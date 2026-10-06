"""Versioned feature endpoints shared by dashboard and acceptance server."""
from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from dsfs.models.demand_feature import FEATURE_VERSION
from dsfs.contracts import load_schema

class Pair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_key: str = Field(min_length=1)
    forecast_cutoff: datetime
    @field_validator("forecast_cutoff")
    @classmethod
    def weekly_utc(cls, value):
        from datetime import timezone
        if value.tzinfo is None:
            raise ValueError("Cutoff requires an explicit timezone")
        value = value.astimezone(timezone.utc)
        if value.weekday() != 0 or (value.hour, value.minute, value.second, value.microsecond) != (0,0,0,0):
            raise ValueError("Cutoff must be Monday 00:00 UTC")
        return value

class HistoricalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    feature_set_version: str = FEATURE_VERSION
    pairs: list[Pair] = Field(min_length=1, max_length=1000)
    horizons: list[Annotated[int, Field(ge=1, le=4)]] = Field(default_factory=lambda:[1,2,3,4], min_length=1)

class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    feature_set_version: str = FEATURE_VERSION
    entity_keys: list[str] = Field(min_length=1, max_length=1000)
    forecast_cutoff: datetime
    horizons: list[Annotated[int, Field(ge=1, le=4)]] = Field(default_factory=lambda:[1,2,3,4], min_length=1)

def feature_router(resolve_service):
    router = APIRouter()
    def retrieve(request):
        if request.feature_set_version != FEATURE_VERSION:
            raise HTTPException(404, "Unknown feature version")
        pairs = [(p.entity_key, p.forecast_cutoff) for p in request.pairs]
        if len(set(pairs)) != len(pairs) or len(set(request.horizons)) != len(request.horizons):
            raise HTTPException(422, "Duplicate account/cutoff or horizon")
        try:
            service = resolve_service(request.run_id)
            return {"run_id": request.run_id, "feature_set_version": FEATURE_VERSION,
                    "features": [service.row(e,c,h).model_dump(mode="json") for e,c in pairs for h in request.horizons]}
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (OSError, RuntimeError) as exc:
            raise HTTPException(503, "Feature snapshot unavailable") from exc
        except Exception as exc:
            raise HTTPException(503, "Feature service failed") from exc
    @router.post("/v1/historical-features:retrieve")
    def historical(request: HistoricalRequest):
        return retrieve(request)
    @router.post("/v1/features:batchGet")
    def batch(request: BatchRequest):
        from pydantic import ValidationError
        try:
            history = HistoricalRequest(run_id=request.run_id, feature_set_version=request.feature_set_version,
                pairs=[Pair(entity_key=e, forecast_cutoff=request.forecast_cutoff) for e in request.entity_keys],
                horizons=request.horizons)
        except ValidationError as exc:
            raise HTTPException(422, "Invalid weekly request") from exc
        return retrieve(history)
    @router.get("/v1/feature-sets/{version}")
    def description(version: str):
        if version != FEATURE_VERSION:
            raise HTTPException(404, "Unknown feature version")
        return load_schema("demand_feature")
    @router.get("/v1/lineage/{run_id}/{signal_id}")
    def lineage(run_id: str, signal_id: str):
        try:
            service = resolve_service(run_id)
            signal = next((s for s in service.signals if s.signal_id == signal_id), None)
            if signal is None:
                raise KeyError("Unknown signal")
            source = service.sources[signal.source_id]
            if source.source_revision != signal.source_revision:
                raise RuntimeError("Lineage source revision mismatch")
            return {"run_id":run_id,"signal":signal.model_dump(mode="json"),"source":source.model_dump(mode="json")}
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(503, "Lineage unavailable") from exc
    return router
