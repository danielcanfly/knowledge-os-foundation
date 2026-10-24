"""C1-35 per-delivery proof freshness adversarial contract, offline only."""
import sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'/'knowledge_engine'))
import m27_c1_dev_minimax_a05_e2e as dev
class CurrentRightsFreshness(unittest.TestCase):
    def setUp(self):
        self.proofs=[{'obligation_id':'one','rights_epoch':7,'tenant':'owner-internal','sha256':'a'},{'obligation_id':'two','rights_epoch':7,'tenant':'owner-internal','sha256':'b'}]
        self.original=dev.digest(dev.canon(self.proofs))
    def check_changed(self, replacement):
        calls=[]
        def reread():
            calls.append(1)
            return replacement
        obj=SimpleNamespace(deadline_ns=1000,live=SimpleNamespace(_source=reread,pending={'source_proofs_sha256':self.original}))
        with patch.object(dev.time,'monotonic_ns',side_effect=[100,200]):
            with self.assertRaisesRegex(ValueError,'F03_A05_RIGHTS_REVOKED'):
                dev.Server.current(obj)
        self.assertEqual(len(calls),1)
    def test_revoked_epoch_cannot_reuse_prior_proofs(self):
        self.check_changed([dict(x,rights_epoch=8) for x in self.proofs])
    def test_cross_tenant_proof_fails_closed(self):
        self.check_changed([dict(x,tenant='other-tenant') for x in self.proofs])
    def test_document_byte_sha_change_fails_closed(self):
        self.check_changed([dict(self.proofs[0],sha256='tampered'),self.proofs[1]])
    def test_deadline_during_source_io_fails_closed(self):
        calls=[]
        def source():
            calls.append(1)
            return self.proofs
        obj=SimpleNamespace(deadline_ns=1000,live=SimpleNamespace(_source=source,pending={'source_proofs_sha256':self.original}))
        with patch.object(dev.time,'monotonic_ns',side_effect=[900,1100]):
            with self.assertRaisesRegex(ValueError,'C1_ONE_TASK_30_SECOND_DEADLINE'):
                dev.Server.current(obj)
        self.assertEqual(calls,[1])
if __name__=='__main__': unittest.main()
