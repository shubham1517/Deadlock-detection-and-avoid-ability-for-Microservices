from pydantic import BaseModel
from typing import Optional
import time

# Tiny rolling 64-bit path digest for "graph summarization"
def roll_digest(prev: int, part: str) -> int:
    h = prev ^ (hash(part) & 0xFFFFFFFFFFFFFFFF)
    # mix (xorshift)
    h ^= (h << 13) & 0xFFFFFFFFFFFFFFFF
    h ^= (h >> 7)
    h ^= (h << 17) & 0xFFFFFFFFFFFFFFFF
    return h & 0xFFFFFFFFFFFFFFFF

class AcquireRequest(BaseModel):
    tx: str          # transaction id (unique per client)
    res: str         # resource id
    ttl_ms: int = 60000  # optional timeout

class ReleaseRequest(BaseModel):
    tx: str
    res: str

class AbortRequest(BaseModel):
    tx: str

class Probe(BaseModel):
    initiator_tx: str        # who started the probe (the blocked transaction)
    origin_service: str      # which service started it
    current_tx: str          # the TX we believe holds a resource this initiator waits on
    current_service: str     # where that tx lives
    path_digest: int         # 64-bit digest summarizing path so far
    hops: int                # hop count guard
    ts_ms: int               # start timestamp (for victim policy)

class ProbeReply(BaseModel):
    deadlock: bool
    cycle: Optional[list[str]] = None   # optional cycle breadcrumb (TX ids)
    victim_tx: Optional[str] = None
    reason: Optional[str] = None
