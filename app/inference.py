"""Inference from original NumPy parameters; never trains on API startup."""
import hashlib
import json
from pathlib import Path

import numpy as np


class Predictor:
    def __init__(self, directory: Path):
        manifest = json.loads((directory / "manifest.json").read_text())
        for name, digest in manifest.items():
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Model integrity failed: {name}")
        self.metadata = json.loads((directory / "configuracion_y_entorno.json").read_text())
        self.gates = json.loads((directory / "criterios_aceptacion.json").read_text())
        self.metrics = json.loads((directory / "metricas_prueba_final.json").read_text())
        with np.load(directory / "modelos.npz", allow_pickle=False) as artifact:
            self.params = {key: artifact[key].copy() for key in artifact.files}
        self.threshold = float(self.metadata["umbral_final_oof"])
        self.version = manifest["modelos.npz"][:12]

    def predict(self, rows):
        x = np.array([[row[k] for k in self.metadata["features"]] for row in rows], dtype=float)
        xr = np.array([[row[k] for k in self.metadata["risk_features"]] for row in rows], dtype=float)
        p = self.params
        zr = np.column_stack([np.ones(len(x)), (x - p["ridge_mean"]) / p["ridge_std"]])
        zl = np.column_stack([np.ones(len(xr)), (xr - p["logistic_mean"]) / p["logistic_std"]])
        with np.errstate(over="raise", invalid="raise"):
            demand = np.maximum(0, np.expm1(zr @ p["ridge_coef"]))
            prob = 1 / (1 + np.exp(-np.clip(zl @ p["logistic_coef"], -35, 35)))
        if not np.isfinite(demand).all():
            raise ValueError("Nonfinite prediction")
        return [{"demanda_semanal": values.tolist(), "demanda_total_4_semanas": float(values.sum()),
                 "probabilidad_faltante": float(score), "alerta": bool(score >= self.threshold)}
                for values, score in zip(demand, prob)]
