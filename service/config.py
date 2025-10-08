import os

SERVICE_NAME = os.getenv("SERVICE_NAME", "svca")
PORT = int(os.getenv("PORT", "8000"))

def _port_for(name: str) -> int:
    return 8000 if name == 'svca' else 8001 if name == 'svcb' else 8002

_raw = os.getenv("PEERS", "")
peer_tokens = [p.strip() for p in _raw.split(",") if p.strip()]

PEERS = []
for tok in peer_tokens:
    if tok.startswith("http://") or tok.startswith("https://"):
        PEERS.append(tok)
    else:
        PEERS.append(f"http://{tok}:{_port_for(tok)}")