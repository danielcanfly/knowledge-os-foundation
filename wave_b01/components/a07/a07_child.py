"""Independent OS-process witness, intentionally refuses to print fixture payload."""
from pathlib import Path
import sys
import time
from a07_memory import MemoryStore, Denied

root,ready,resume=map(Path,sys.argv[1:])
before=MemoryStore(root)
assert before.candidate(tenant="A",principal="alice",memid="m1")["citation_eligible"] is False
assert before.query_cache(tenant="A",principal="alice",key="c1")
ready.touch()
limit=time.monotonic()+10
while not resume.exists() and time.monotonic()<limit:
    time.sleep(.025)
assert resume.exists(), "resume was not received"
after=MemoryStore(root)
operations=[
    lambda:after.candidate(tenant="A",principal="alice",memid="m1"),
    lambda:after.query_cache(tenant="A",principal="alice",key="c1"),
    lambda:after.read_source(tenant="A",principal="alice",source="s1")
]
for operation in operations:
    try:
        operation()
    except Denied:
        pass
    else:
        raise AssertionError("FAILED_REVOCATION_FENCE")
print("CHILD_RESTART_REVOKED_DENIED=3")
