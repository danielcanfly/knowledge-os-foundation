"""Nonprod C1 external-custody boot wiring checks, NOT Product signoff.

No real/private/test signing keys created or accepted by this suite.
"""
from __future__ import annotations

import inspect
from pathlib import Path
import sys
from unittest import TestCase, main
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "knowledge_engine"))
import m27_c1_current_native_product_nonprod as app
import m27_c1_genuine_native_generation_seam as seam


class ExternalAuthorityBootWiring(TestCase):
    def test_01_official_paths_exposed_at_adapter_boundary(self):
        for callable_ in (app.Candidate, app.serve):
            names = inspect.signature(callable_).parameters
            self.assertIn("trust_root_file", names)
            self.assertIn("qualification_bundle_file", names)

    def test_02_paths_forwarded_to_authority_without_minting_keys(self):
        public_root = Path("/nonprod/issuer/release-approved-root.json")
        signed_grants = Path("/nonprod/issuer/externally-signed-grants.json")
        with patch.object(app, "source_vector", return_value={"head": "a" * 40}), \
             patch.object(app, "read_client_capability", return_value=b"x" * 40), \
             patch.object(app.h02, "Consumer") as h02consumer, \
             patch.object(app.native_live, "NativeLiveProduct") as native:
            h02consumer.return_value.recovery = "EMPTY"
            app.Candidate(repo=Path("/no-touch-repo"), fence=Path("/no-touch-fence"),
                          journal=Path("/no-touch-journal"), token_file=Path("/no-touch-token"),
                          expected_head="a" * 40, expected_tree="b" * 40,
                          trust_root_file=public_root,
                          qualification_bundle_file=signed_grants)
            self.assertEqual(native.call_args.kwargs["trust_root"], public_root)
            self.assertEqual(native.call_args.kwargs["qualification_bundle"], signed_grants)

    def test_03_default_still_no_external_authority(self):
        with patch.object(app, "source_vector", return_value={"head": "a" * 40}), \
             patch.object(app, "read_client_capability", return_value=b"x" * 40), \
             patch.object(app.h02, "Consumer") as h02consumer, \
             patch.object(app.native_live, "NativeLiveProduct") as native:
            h02consumer.return_value.recovery = "EMPTY"
            app.Candidate(repo=Path("/no-touch-repo"), fence=Path("/no-touch-fence"),
                          journal=Path("/no-touch-journal"), token_file=Path("/no-touch-token"),
                          expected_head="a" * 40, expected_tree="b" * 40)
            self.assertIsNone(native.call_args.kwargs["trust_root"])
            self.assertIsNone(native.call_args.kwargs["qualification_bundle"])

    def test_04_paths_cannot_bypass_unapproved_compile_time_root(self):
        self.assertIsNone(seam.TRUST_ROOT_MANIFEST_SHA256)
        with self.assertRaisesRegex(seam.NotQualified, "INDEPENDENT_TRUST_ROOT_NOT_ADMITTED"):
            seam.IndependentAuthority(Path("/no-touch-pretend-release-root.json"))


if __name__ == "__main__":
    main()
