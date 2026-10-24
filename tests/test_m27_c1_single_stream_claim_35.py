"""C1 atomic native SSE admission. No external provider calls."""
import concurrent.futures
import inspect
import sys
import threading
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"/"knowledge_engine"))
import m27_c1_dev_minimax_a05_e2e as dev

class AtomicSingleStreamAdmission(unittest.TestCase):
    def test_handler_calls_atomic_claim_not_check_then_set(self):
        body=inspect.getsource(dev.Handler.do_GET)
        self.assertIn("s.claim_stream_once()",body)
        self.assertNotIn("or s.once:",body)
    def test_fifty_parallel_claims_admit_exactly_one(self):
        fake=object.__new__(dev.Server)
        fake.once=False
        fake.stream_claim_lock=threading.Lock()
        barrier=threading.Barrier(50)
        def race(_):
            barrier.wait(timeout=8)
            return dev.Server.claim_stream_once(fake)
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
            decisions=list(pool.map(race,range(50)))
        self.assertEqual(decisions.count(True),1)
        self.assertEqual(decisions.count(False),49)
        self.assertTrue(fake.once)
        self.assertFalse(dev.Server.claim_stream_once(fake))
    def test_separate_server_instances_get_independent_claims(self):
        objects=[]
        for _ in range(2):
            s=object.__new__(dev.Server)
            s.once=False;s.stream_claim_lock=threading.Lock()
            objects.append(s)
        self.assertTrue(dev.Server.claim_stream_once(objects[0]))
        self.assertTrue(dev.Server.claim_stream_once(objects[1]))
        self.assertFalse(dev.Server.claim_stream_once(objects[0]))
        self.assertFalse(dev.Server.claim_stream_once(objects[1]))

if __name__=="__main__":unittest.main()
