When microservices grab resources in different places at the same time, they can accidentally block each other forever—a distributed deadlock. I built a small, container-friendly detector that notices these “you’re waiting on me while I’m waiting on you” situations without needing a big, centralized view of the whole system. It sends tiny probe messages, recognizes cycles using a compact fingerprint (rolling digest), and automatically aborts one transaction so the system unfreezes. It’s simple to run, easy to demo, and mirrors the classic edge-chasing idea from distributed systems.

⸻

1) Problem & why it matters

Modern apps are stitched from many services: config, inventory, IPAM, billing, etc. A single request may lock several of them. If two requests lock different pieces and then each needs what the other holds, you get a cycle. Timeouts waste work and feel random. Centralized detectors need global state and become a bottleneck. I wanted something decentralized, lightweight, and practical for containers.

2) What I built (short version)
	•	One detector sidecar per service (no central coordinator).
	•	When a request blocks, the sidecar launches a probe that follows “who waits on whom.”
	•	Each probe carries a rolling digest (tiny fingerprint) instead of a full path.
	•	If the probe loops back to the starter, that’s a deadlock. We pick a victim and abort it.
	•	Everything runs in Docker Compose with three sample services and Prometheus metrics.

3) How it works (in human words)
	1.	Transaction A is blocked by B → send a small probe that says “follow B.”
	2.	If B is blocked by C, the probe is forwarded to follow C, and so on.
	3.	The probe’s fingerprint (digest) is updated each hop. That keeps messages tiny and lets us drop duplicates.
	4.	If the probe ever comes back to A, we’ve found a loop → abort a victim → system moves again.

4) API (each service exposes)
	•	POST /acquire {tx, res} → try to lock a resource (granted or blocked)
	•	POST /release {tx, res} → release a resource
	•	POST /abort {tx} → abort a transaction (cleans queues, releases locks)
	•	POST /probe { ... } → handle/forward a probe, maybe declare deadlock
	•	GET /wfg → show local wait-for edges
	•	GET /metrics → counters: acquire_total, blocked_total, deadlocks_total, aborts_total

5) Under the hood (key ideas)
	•	Edge-chasing (Chandy–Misra–Haas flavor): detect cycles by walking wait edges, not by building a global graph.
	•	Graph summarization: per-initiator set of 64-bit digests → constant memory and bounded traffic.
	•	Two ways we declare a deadlock:
	•	Direct loopback: probe’s current_tx == initiator_tx (and we took at least one hop).
	•	Classic check: a probe with hops > 1 reaches a node that still sees the initiator blocked.
	•	Auto-heal: choose a victim (younger transaction by age) and broadcast /abort (local first, then peers).
	•	Safety guard: if a transaction accidentally blocks on itself (non-reentrant lock), we don’t launch distributed probes.

6) Test setup (what I ran)
	•	Three services: svca:8000, svcb:8001, svcc:8002.
	•	2-node deadlock:
	•	A.t1 holds R1 on svca, B.t2 holds R2 on svcb.
	•	Then A.t1 requests R2 from svcb, and B.t2 requests R1 from svca (cross-service waits).
	•	I “re-poked” the same blocked acquires once to make sure probes run after both edges exist.
	•	I observed /wfg before/after, deadlocks_total/aborts_total, and logs (which print probe send/forward and DEADLOCK(...) lines).

7) Results (summary)
	•	The detector reliably found the A↔B cycle; logs showed DEADLOCK(direct) or DEADLOCK(classic).
	•	A victim was aborted, /wfg cleared, and metrics increased (deadlocks_total, aborts_total).
	•	Digest dedupe prevented probe storms—only a few small messages per detection.
	•	Occasionally a stale local edge remained right after recovery (race); a targeted /abort on that service cleared it.

8) Why this is correct (and safe)
	•	A cycle is only reported when the probe walks a loop back to its origin or reaches a node that still sees the origin blocked after multiple hops—both imply a real cycle in the global wait-for graph.
	•	Liveness: any persistent block will eventually trigger (or re-trigger) probes, and aborting one victim breaks the cycle.

9) Cost & limits (honest take)
	•	Messages: ~one forward per edge in the cycle, plus small fan-outs; dedupe keeps it tame.
	•	Memory: small per-initiator set of 64-bit digests.
	•	Timing: best-effort HTTP; if a probe is lost right before the second edge forms, a quick re-poke (or timer in production) resolves it.
	•	Scope: prototype uses HTTP fan-out to all peers; a real deployment could use membership/gossip to trim destinations.
