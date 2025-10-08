import httpx
from typing import Dict, Set
from common.proto import Probe, ProbeReply, roll_digest
from .config import SERVICE_NAME, PEERS
from .lock_mgr import LockManager

MAX_HOPS = 64  # guard against probe storms


class Detector:
    """
    Decentralized deadlock detector using edge-chasing probes.

    - Graph summarization: per-initiator dedupe via a 64-bit rolling path_digest.
    - Direct cycle check: if a probe loops back to the initiator, declare deadlock.
    - Classic check: initiator still blocked here with hops>1 implies a cycle.
    - Auto-heal: choose a victim and broadcast /abort (local first, then peers).
    """

    def __init__(self, lm: LockManager):
        self.lm = lm
        # initiator_tx -> set of path digests we've already seen
        self.seen_digests: Dict[str, Set[int]] = {}

    def _mark_seen(self, initiator: str, digest: int) -> bool:
        s = self.seen_digests.setdefault(initiator, set())
        if digest in s:
            return False
        s.add(digest)
        return True

    def _choose_victim(self, tx_a: str, tx_b: str | None) -> str:
        """
        Abort the 'younger' transaction by default (smaller age).
        If tx_b is None (no holder known), fall back to tx_a.
        """
        if tx_b is None:
            return tx_a
        age_a = self.lm.tx_age_ms(tx_a)
        age_b = self.lm.tx_age_ms(tx_b)
        return tx_a if age_a < age_b else tx_b

    async def _broadcast_abort(self, tx: str):
        """
        Abort locally, then ask peers to abort. Best-effort network.
        """
        self.lm.abort(tx)
        async with httpx.AsyncClient(timeout=2.0) as client:
            for peer in PEERS:
                try:
                    await client.post(f"{peer}/abort", json={"tx": tx})
                except Exception as e:
                    print(f"[{SERVICE_NAME}] abort send error to {peer}: {e}")

    async def start_probe(self, blocked_tx: str, holder_tx: str, ts_ms: int):
        """
        Start a probe from 'blocked_tx' toward 'holder_tx' and fan out to peers.
        """
        if blocked_tx == holder_tx:
            print(f"[{SERVICE_NAME}] skip probe for self-wait: {blocked_tx}")
            return
        digest = roll_digest(0, f"{blocked_tx}->{holder_tx}")
        probe = Probe(
            initiator_tx=blocked_tx,
            origin_service=SERVICE_NAME,
            current_tx=holder_tx,
            current_service="unknown",
            path_digest=digest,
            hops=1,
            ts_ms=ts_ms,
        )

        print(f"[{SERVICE_NAME}] start_probe: {blocked_tx} -> {holder_tx}; peers={PEERS}")
        async with httpx.AsyncClient(timeout=2.0) as client:
            for peer in PEERS:
                try:
                    print(f"[{SERVICE_NAME}] sending /probe to {peer}")
                    await client.post(f"{peer}/probe", json=probe.model_dump())
                except Exception as e:
                    print(f"[{SERVICE_NAME}] probe send error to {peer}: {e}")

    async def on_probe(self, probe: Probe) -> ProbeReply:
        """
        Handle an incoming probe:

          1) Dedupe by (initiator, path_digest).
          2) Direct-cycle: if probe.current_tx == initiator, declare deadlock.
          3) Classic: if initiator still blocked here and hops>1, declare deadlock.
          4) Else, if current_tx is blocked locally on 'next_holder', forward.
        """
        # 1) Dedupe
        if not self._mark_seen(probe.initiator_tx, probe.path_digest):
            return ProbeReply(deadlock=False, reason="duplicate_digest")

        # 2) Direct-cycle: probe looped back to initiator
        if probe.current_tx == probe.initiator_tx and probe.hops >= 1:
            holder = None
            for w, h in self.lm.blocked_tx():
                if w == probe.initiator_tx:
                    holder = h
                    break
            victim = self._choose_victim(probe.initiator_tx, holder)
            print(f"[{SERVICE_NAME}] DEADLOCK(direct): initiator={probe.initiator_tx} victim={victim} hops={probe.hops}")
            await self._broadcast_abort(victim)
            # clean digests for this initiator so future probes aren't suppressed
            self.seen_digests.pop(probe.initiator_tx, None)
            return ProbeReply(deadlock=True, cycle=[probe.initiator_tx], victim_tx=victim)

        # 3) Classic condition: initiator is still blocked here and path length > 1
        for w, h in self.lm.blocked_tx():
            if w == probe.initiator_tx and probe.hops > 1:
                victim = self._choose_victim(probe.initiator_tx, h)
                print(f"[{SERVICE_NAME}] DEADLOCK(classic): initiator={probe.initiator_tx} holder={h} victim={victim} hops={probe.hops}")
                await self._broadcast_abort(victim)
                self.seen_digests.pop(probe.initiator_tx, None)
                return ProbeReply(deadlock=True, cycle=[probe.initiator_tx], victim_tx=victim)

        # 4) Forward if current_tx is blocked locally
        next_holder = None
        for w, h in self.lm.blocked_tx():
            if w == probe.current_tx:
                next_holder = h
                break

        if next_holder is None:
            return ProbeReply(deadlock=False, reason="no_next_edge")

        if probe.hops + 1 > MAX_HOPS:
            return ProbeReply(deadlock=False, reason="max_hops")

        new_digest = roll_digest(probe.path_digest, f"{probe.current_tx}->{next_holder}")
        fwd = probe.model_copy(
            update={
                "current_tx": next_holder,
                "current_service": "unknown",
                "path_digest": new_digest,
                "hops": probe.hops + 1,
            }
        )

        print(f"[{SERVICE_NAME}] forward probe: {probe.current_tx} -> {next_holder}; hops={fwd.hops}")
        async with httpx.AsyncClient(timeout=2.0) as client:
            for peer in PEERS:
                try:
                    print(f"[{SERVICE_NAME}] forwarding /probe to {peer}")
                    await client.post(f"{peer}/probe", json=fwd.model_dump())
                except Exception as e:
                    print(f"[{SERVICE_NAME}] probe forward error to {peer}: {e}")

        return ProbeReply(deadlock=False, reason="forwarded")