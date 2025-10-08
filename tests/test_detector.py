import asyncio
from service.lock_mgr import LockManager
from service.detector import Detector

def test_victim_selection_younger_is_aborted(monkeypatch):
    lm = LockManager("test")
    d = Detector(lm)
    lm.acquire("old","R1")
    lm.acquire("young","R2")
    # block each other
    lm.acquire("old","R2")   # blocked on young
    lm.acquire("young","R1") # blocked on old
    # young should be younger; force ages
    lm.start_ts["old"] -= 10000

    # monkeypatch broadcast abort to just call local abort
    async def fake_broadcast(tx):
        lm.abort(tx)
    monkeypatch.setattr(d, "_broadcast_abort", fake_broadcast)

    # Simulate probe returning to initiator (hops > 1)
    class ProbeLike:
        initiator_tx = "old"
        current_tx = "young"
        current_service = "unknown"
        origin_service = "test"
        path_digest = 0
        hops = 2
        ts_ms = lm._now()

    reply = asyncio.get_event_loop().run_until_complete(d.on_probe(ProbeLike()))
    assert reply.deadlock
    assert reply.victim_tx == "young"
