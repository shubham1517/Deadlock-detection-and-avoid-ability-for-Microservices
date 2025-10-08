import time
from collections import deque, defaultdict
from typing import Dict, Deque, Optional, Tuple, List

class LockManager:
    """
    Simple FIFO mutex per resource.
    Tracks owners and waiters to derive local wait-for edges.
    Also supports aborting a transaction (auto-abort hook).
    """
    def __init__(self, service_name: str):
        self.service = service_name
        self.owners: Dict[str, str] = {}             # res -> tx
        self.queues: Dict[str, Deque[str]] = defaultdict(deque)  # res -> waiters
        self.start_ts: Dict[str, int] = {}           # tx -> first seen (ms)
        self.waiting_on: Dict[str, Optional[str]] = {}  # tx -> res or None

    def _now(self) -> int:
        return int(time.time() * 1000)

    def acquire(self, tx: str, res: str) -> Tuple[bool, Optional[str]]:
        self.start_ts.setdefault(tx, self._now())
        holder = self.owners.get(res)
        if holder is None:
            self.owners[res] = tx
            self.waiting_on[tx] = None
            return True, None
        elif holder == tx:
            # Re-entrant acquire: same tx can re-grab without blocking
            self.waiting_on[tx] = None
            return True, None
        else:
            # already held; enqueue
            # avoid duplicate enqueue for same res
            if tx not in self.queues[res]:
                self.queues[res].append(tx)
            self.waiting_on[tx] = res
            return False, holder

    def release(self, tx: str, res: str) -> bool:
        if self.owners.get(res) != tx:
            return False
        if self.queues[res]:
            nxt = self.queues[res].popleft()
            self.owners[res] = nxt
            self.waiting_on[nxt] = None
        else:
            del self.owners[res]
        return True

    def holder_for(self, res: str) -> Optional[str]:
        return self.owners.get(res)

    def blocked_tx(self) -> List[tuple]:
        edges = []
        for res, q in self.queues.items():
            if q and res in self.owners:
                holder = self.owners[res]
                for w in list(q):
                    edges.append((w, holder))
        return edges

    def tx_age_ms(self, tx: str) -> int:
        return self._now() - self.start_ts.get(tx, self._now())

    def abort(self, tx: str) -> int:
        """
        Abort a transaction: remove from wait queues and release owned locks.
        Returns count of affected resources.
        """
        affected = 0
        # Remove from waiting queues
        for res, q in self.queues.items():
            if tx in q:
                try:
                    q.remove(tx)
                    affected += 1
                except ValueError:
                    pass
        # Release owned resources
        owned = [r for r, owner in list(self.owners.items()) if owner == tx]
        for r in owned:
            self.release(tx, r)
            affected += 1
        # Cleanup
        self.waiting_on.pop(tx, None)
        self.start_ts.pop(tx, None)
        return affected
