from fastapi import FastAPI, HTTPException
from typing import Dict
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from common.proto import AcquireRequest, ReleaseRequest, AbortRequest, Probe, ProbeReply
from .lock_mgr import LockManager
from .detector import Detector
from .config import SERVICE_NAME

app = FastAPI(title=f"{SERVICE_NAME}-svc")

lm = LockManager(SERVICE_NAME)
det = Detector(lm)

# --- Metrics ---
registry = CollectorRegistry()
acquire_total = Counter('acquire_total', 'Total acquire attempts', ['service'], registry=registry)
blocked_total = Counter('blocked_total', 'Total blocked acquires', ['service'], registry=registry)
release_total = Counter('release_total', 'Total releases', ['service'], registry=registry)
deadlocks_total = Counter('deadlocks_total', 'Total deadlocks detected', ['service'], registry=registry)
aborts_total = Counter('aborts_total', 'Total tx aborts', ['service'], registry=registry)

@app.get("/metrics")
def metrics():
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

@app.get("/health")
def health():
    return {"service": SERVICE_NAME, "status": "ok"}

@app.post("/acquire")
async def acquire(req: AcquireRequest):
    acquire_total.labels(SERVICE_NAME).inc()
    ok, holder = lm.acquire(req.tx, req.res)
    if ok:
        return {"granted": True, "holder": req.tx}
    else:
        blocked_total.labels(SERVICE_NAME).inc()
        await det.start_probe(req.tx, holder, lm._now())
        return {"granted": False, "blocked_on": holder}

@app.post("/release")
async def release(req: ReleaseRequest):
    if not lm.release(req.tx, req.res):
        raise HTTPException(status_code=409, detail="not owner")
    release_total.labels(SERVICE_NAME).inc()
    return {"released": True}

@app.post("/abort")
def abort(req: AbortRequest):
    affected = lm.abort(req.tx)
    aborts_total.labels(SERVICE_NAME).inc()
    return {"aborted": req.tx, "affected": affected}

@app.post("/probe", response_model=ProbeReply)
async def probe(p: Probe):
    reply = await det.on_probe(p)
    if reply.deadlock:
        deadlocks_total.labels(SERVICE_NAME).inc()
    return reply

@app.get("/wfg")
def wait_for_graph():
    return {"service": SERVICE_NAME, "edges": lm.blocked_tx()}
@app.post("/probe", response_model=ProbeReply)
async def probe(p: Probe):
    reply = await det.on_probe(p)
    if reply.deadlock:
        deadlocks_total.labels(SERVICE_NAME).inc()
        print(f"[{SERVICE_NAME}] probe -> DEADLOCK: victim={reply.victim_tx}")
    return reply