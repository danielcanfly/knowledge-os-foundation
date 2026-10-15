"""Reproduce a real baseline M28 limitation in isolated local fixture copies.

Expected to fail: old run-scoped revoke cannot preserve independent source s2.
This is evidence of old API granularity, not a regression of the old release.
"""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile

old = Path("/Users/huaihsuanhuang/Desktop/Chatgpt/M27/"
           "M27_VNEXT_MASTER_20261009/06_WORKSITES/"
           "Q33_PUBLICATION_GATE_CANDIDATE_20261013/src/"
           "knowledge_engine/m27_m28_local_rights_memory_fence.py")
sha=hashlib.sha256(old.read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location("m28_readonly_fence",old)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix="m28_before_", dir=Path(__file__).parent) as d:
    root=Path(d)
    fence=module.LocalRightsMemoryFence(root/"fence.sqlite",root/"blobs",fixture_only=True)
    lease=fence.grant(tenant="A",run="r1",principal="alice",purpose="research",
                      revision="v1",lease_id="lease1")
    fence.put(lease,"s1","source",b"first")
    fence.put(lease,"s2","source",b"independent")
    fence.revoke(lease)
    print(f"BASELINE_M28_SHA256={sha}")
    print("EXPECTED_OLD_DEFECT: scope-wide revoke denies even independent s2")
    try:
        fence.read(lease,"s2")
    except module.LifecycleDenied as e:
        print("BEFORE_FAIL=NO_SOURCE_SCOPED_REVOCATION",str(e))
        sys.exit(1)
    else:
        print("BEFORE_PASS=INDEPENDENT_SOURCE_SURVIVED")
        sys.exit(0)
