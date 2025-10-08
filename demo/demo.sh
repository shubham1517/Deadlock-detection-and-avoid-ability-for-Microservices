# Clean any stale tx
curl -s -X POST localhost:8000/abort -H 'content-type: application/json' -d '{"tx":"A.t1"}'
curl -s -X POST localhost:8001/abort -H 'content-type: application/json' -d '{"tx":"B.t2"}'

# Seed locks
curl -s -X POST localhost:8000/acquire -H 'content-type: application/json' -d '{"tx":"A.t1","res":"R1"}'
curl -s -X POST localhost:8001/acquire -H 'content-type: application/json' -d '{"tx":"B.t2","res":"R2"}'

# Create cross waits
curl -s -X POST localhost:8001/acquire -H 'content-type: application/json' -d '{"tx":"A.t1","res":"R2"}'
curl -s -X POST localhost:8000/acquire -H 'content-type: application/json' -d '{"tx":"B.t2","res":"R1"}'

# Re-poke (ensures probes are launched after both edges exist)
curl -s -X POST localhost:8001/acquire -H 'content-type: application/json' -d '{"tx":"A.t1","res":"R2"}'
curl -s -X POST localhost:8000/acquire -H 'content-type: application/json' -d '{"tx":"B.t2","res":"R1"}'

sleep 4

# Verify
curl -s localhost:8000/wfg ; echo
curl -s localhost:8001/wfg ; echo
curl -s localhost:8000/metrics | egrep "deadlocks_total|aborts_total"
curl -s localhost:8001/metrics | egrep "deadlocks_total|aborts_total"