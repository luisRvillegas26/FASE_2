import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.inference import Predictor

MODEL_DIR = Path(os.getenv("MODEL_DIR", Path(__file__).resolve().parents[1] / "model"))
API_KEY = os.getenv("API_KEY", "")
logger = logging.getLogger("uvicorn.error")


class Features(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    log_reciente: float = Field(ge=0, le=20)
    tendencia: float = Field(ge=-5, le=5)
    log_anual: float = Field(ge=0, le=20)
    sin_1: float = Field(ge=-1, le=1)
    cos_1: float = Field(ge=-1, le=1)
    sin_2: float = Field(ge=-1, le=1)
    cos_2: float = Field(ge=-1, le=1)
    promocion: float = Field(ge=0, le=1)
    log_precio_relativo: float = Field(ge=-5, le=5)
    log_escala: float = Field(ge=0, le=20)
    canal_farmacia: int = Field(ge=0, le=1, strict=True)
    canal_ecommerce: int = Field(ge=0, le=1, strict=True)
    region_norte: int = Field(ge=0, le=1, strict=True)
    region_sur: int = Field(ge=0, le=1, strict=True)
    disponibilidad: float = Field(ge=0, le=1)
    log_oferta_relativa: float = Field(ge=-20, le=20)

    @model_validator(mode="after")
    def exclusive_categories(self):
        if self.canal_farmacia + self.canal_ecommerce > 1 or self.region_norte + self.region_sur > 1:
            raise ValueError("Las categorias de canal y region deben ser excluyentes")
        return self


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instances: list[Features] = Field(min_length=1, max_length=100)


class Prediction(BaseModel):
    demanda_semanal: list[float] = Field(min_length=4, max_length=4)
    demanda_total_4_semanas: float
    probabilidad_faltante: float
    alerta: bool


class PredictResponse(BaseModel):
    model_version: str
    synthetic: bool
    operationally_approved: bool
    umbral: float
    predictions: list[Prediction]


def authorize(x_api_key: Annotated[str | None, Header()] = None):
    if API_KEY and not secrets.compare_digest(x_api_key or "", API_KEY):
        raise HTTPException(status_code=401, detail="API key invalida")


@asynccontextmanager
async def lifespan(app):
    app.state.predictor = Predictor(MODEL_DIR)
    logger.info("Model loaded version=%s synthetic=true", app.state.predictor.version)
    yield
    app.state.predictor = None


app = FastAPI(title="Opella demanda - demostracion sintetica", version="1.0.0", lifespan=lifespan,
              description="Pronostico de 4 semanas y alerta independiente. Sin aprobacion operativa.")


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    if getattr(app.state, "predictor", None) is None:
        raise HTTPException(status_code=503, detail="Modelo no disponible")
    return {"status": "ready", "model_version": app.state.predictor.version}


@app.get("/v1/model", dependencies=[Depends(authorize)])
def model():
    p = app.state.predictor
    return {"version": p.version, "synthetic": True, "operationally_approved": False,
            "features": p.metadata["risk_features"], "umbral": p.threshold,
            "acceptance": p.gates, "test_metrics": p.metrics}


@app.post("/v1/predict", response_model=PredictResponse, dependencies=[Depends(authorize)])
def predict(body: PredictRequest):
    p = app.state.predictor
    try:
        predictions = p.predict([item.model_dump() for item in body.instances])
    except (FloatingPointError, ValueError):
        raise HTTPException(status_code=422, detail="Entrada fuera del dominio numerico del modelo")
    return {"model_version": p.version, "synthetic": True, "operationally_approved": False,
            "umbral": p.threshold, "predictions": predictions}
