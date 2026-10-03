from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED = "M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED"

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class M27FeatureFlags:
    """Resolved M27-only feature flags.

    The object stores only resolved booleans. Raw environment values are never
    retained, logged, or exposed.
    """

    shadow_trace_requested: bool = False
    isolated_runtime: bool = False

    @property
    def context_runtime_shadow_trace_enabled(self) -> bool:
        return self.shadow_trace_requested and self.isolated_runtime


def load_m27_feature_flags(
    *,
    environ: Mapping[str, str] | None = None,
    isolated_runtime: bool = False,
) -> M27FeatureFlags:
    """Resolve M27 feature flags with an explicit isolated-runtime gate.

    Even when the environment requests shadow tracing, the effective flag is
    false unless the caller explicitly identifies the runtime as isolated M27.
    """

    values = os.environ if environ is None else environ
    raw_requested_value = values.get(M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED, "")
    requested = raw_requested_value.strip().casefold() in _TRUE_VALUES
    return M27FeatureFlags(
        shadow_trace_requested=requested,
        isolated_runtime=isolated_runtime,
    )
