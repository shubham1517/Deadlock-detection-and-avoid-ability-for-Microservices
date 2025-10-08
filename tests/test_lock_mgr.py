from service.lock_mgr import LockManager

def test_basic_lock_cycle_and_abort():
    lm = LockManager("test")
    ok, _ = lm.acquire("t1","R1")
    assert ok
    ok, holder = lm.acquire("t2","R1")
    assert not ok and holder=="t1"
    edges = lm.blocked_tx()
    assert ("t2","t1") in edges
    # abort t1 should transfer lock to t2
    lm.abort("t1")
    assert lm.holder_for("R1") == "t2"
