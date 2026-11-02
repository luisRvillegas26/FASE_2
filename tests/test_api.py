import csv
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.inference import Predictor

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads((ROOT / "examples/predict.json").read_text())


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


def test_health_and_metadata(client):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    m = client.get("/v1/model").json()
    assert m["synthetic"] and not m["operationally_approved"]
    assert m["umbral"] == 0.28
    assert "/v1/predict" in client.get("/openapi.json").json()["paths"]


def test_predict(client):
    r = client.post("/v1/predict", json=EXAMPLE)
    assert r.status_code == 200
    p = r.json()["predictions"][0]
    assert len(p["demanda_semanal"]) == 4
    assert sum(p["demanda_semanal"]) == pytest.approx(p["demanda_total_4_semanas"])
    assert p["alerta"] == (p["probabilidad_faltante"] >= 0.28)


@pytest.mark.parametrize("change", ["empty", "missing", "extra", "range", "categories", "oversize"])
def test_invalid_payload(client, change):
    body = json.loads(json.dumps(EXAMPLE))
    item = body["instances"][0]
    if change == "empty": body["instances"] = []
    if change == "missing": del item["log_reciente"]
    if change == "extra": item["demanda_futura"] = 100
    if change == "range": item["disponibilidad"] = 1.5
    if change == "categories": item.update(canal_farmacia=1, canal_ecommerce=1)
    if change == "oversize": body["instances"] *= 101
    assert client.post("/v1/predict", json=body).status_code == 422


def test_api_key(client, monkeypatch):
    monkeypatch.setattr(main, "API_KEY", "temporary-test-key")
    assert client.get("/v1/model").status_code == 401
    assert client.post("/v1/predict", json=EXAMPLE).status_code == 401
    assert client.post("/v1/predict", json=EXAMPLE,
                       headers={"X-API-Key": "temporary-test-key"}).status_code == 200
    assert client.get("/health/ready").status_code == 200


def test_all_reference_predictions_match_original_model(client):
    """432 cases / 1728 forecasts compared with original exported evidence."""
    predictor = Predictor(ROOT / "model")
    with (ROOT / "tests/reference_features.json").open() as f:
        features = json.load(f)
    with (ROOT / "tests/reference_predictions.csv").open() as f:
        expected = list(csv.DictReader(f))
    actual = []
    for start in range(0, len(features), 100):
        response = client.post("/v1/predict", json={"instances": features[start:start+100]})
        assert response.status_code == 200
        actual.extend(response.json()["predictions"])
    assert len(actual) == len(expected) == 432
    for a, e in zip(actual, expected):
        np.testing.assert_allclose(a["demanda_semanal"], [float(e[f"pred_h{h}"]) for h in range(1,5)], rtol=1e-12)
        assert a["probabilidad_faltante"] == pytest.approx(float(e["probabilidad"]), abs=1e-12)
        assert a["alerta"] == bool(int(e["alerta"]))
    assert predictor.threshold == 0.28


def test_corrupt_model_fails_startup(tmp_path):
    import shutil
    shutil.copytree(ROOT / "model", tmp_path / "model")
    (tmp_path / "model/modelos.npz").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        Predictor(tmp_path / "model")
