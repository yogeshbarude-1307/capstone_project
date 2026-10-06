"""Explicit providers: HTTP failures never fall back to local files."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
import json
import socket
import threading
import time
from typing import Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import pandas as pd
from dsfs.models.demand_feature import DemandFeatureRecord, FEATURE_VERSION

class FeatureProvider(Protocol):
    def retrieve(self, pairs: list[tuple[str, datetime]], horizons=(1,2,3,4)) -> pd.DataFrame: ...

class InProcessFeatureProvider:
    def __init__(self, service):
        self.service = service
    def retrieve(self, pairs, horizons=(1,2,3,4)):
        return self.service.historical(pairs, horizons)

class HttpFeatureProvider:
    def __init__(self, base_url, run_id, *, timeout=60):
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Feature provider must use local HTTP")
        self.base_url, self.run_id, self.timeout = base_url.rstrip("/"), run_id, timeout
        self.request_count = 0
    def retrieve(self, pairs, horizons=(1,2,3,4)):
        rows = []
        for offset in range(0, len(pairs), 250):
            chunk = pairs[offset:offset+250]
            payload = {"run_id": self.run_id, "feature_set_version": FEATURE_VERSION,
                       "pairs": [{"entity_key": e, "forecast_cutoff": c.isoformat()} for e,c in chunk],
                       "horizons": list(horizons)}
            request = Request(self.base_url+"/v1/historical-features:retrieve",
                              data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
            # urlopen raises for network and non-2xx errors. No alternative path.
            with urlopen(request, timeout=self.timeout) as response:
                body = json.load(response)
            if body.get("run_id") != self.run_id or body.get("feature_set_version") != FEATURE_VERSION:
                raise ValueError("Feature API returned incompatible run or version")
            batch = [DemandFeatureRecord.model_validate(r).model_dump(mode="json") for r in body["features"]]
            actual = {(r["entity_key"], pd.Timestamp(r["forecast_cutoff"]), r["horizon_step"]) for r in batch}
            expected = {(e, pd.Timestamp(c), h) for e,c in chunk for h in horizons}
            if len(batch) != len(expected) or actual != expected or any(r["run_id"] != self.run_id for r in batch):
                raise ValueError("Feature API returned mismatched or duplicate keys")
            rows.extend(batch)
            self.request_count += 1
        return pd.DataFrame(rows)

@contextmanager
def serve_local(service):
    """Run the same feature routes on an ephemeral loopback socket, then stop."""
    import uvicorn
    from fastapi import FastAPI
    from dsfs.features.http import feature_router
    app = FastAPI()
    def resolve(run_id):
        if run_id != service.run_id:
            raise KeyError("Unknown run")
        return service
    app.include_router(feature_router(resolve))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False, lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets":[sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic()+15
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Local feature API failed to start")
            time.sleep(0.01)
        yield HttpFeatureProvider(f"http://127.0.0.1:{port}", service.run_id)
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("Local feature API did not stop")
