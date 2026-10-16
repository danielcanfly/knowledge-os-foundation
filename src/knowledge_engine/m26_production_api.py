from __future__ import annotations

from .m26_aq_semantic_contract import CANONICAL_RUNTIME_ENTRYPOINT
from .api import app  # noqa: F401
from .m26_translation_gateway_public_api import create_app

app.mount("/", create_app(), name="m26-canonical-answers")

__all__ = ["CANONICAL_RUNTIME_ENTRYPOINT", "app"]
