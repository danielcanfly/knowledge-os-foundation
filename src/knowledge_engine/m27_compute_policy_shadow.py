from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .m27_compute_policy import ComputePolicyObservation, RuleBasedComputePolicy

M27_COMPUTE_POLICY_SHADOW_ENABLED = "M27_COMPUTE_POLICY_SHADOW_ENABLED"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class ComputePolicyShadowFlags:
    requested: bool = False
    isolated_runtime: bool = False

    @property
    def enabled(self) -> bool:
        return self.requested and self.isolated_runtime


def load_compute_policy_shadow_flags(
    *,
    environ: Mapping[str, str] | None = None,
    isolated_runtime: bool = False,
) -> ComputePolicyShadowFlags:
    """Resolve the Stage 4 flag without retaining or exposing raw environment values."""

    values = os.environ if environ is None else environ
    raw_value = values.get(M27_COMPUTE_POLICY_SHADOW_ENABLED, "")
    requested = raw_value.strip().casefold() in _TRUE_VALUES
    return ComputePolicyShadowFlags(
        requested=requested,
        isolated_runtime=isolated_runtime,
    )


def classify_shadow_compute(
    budget_signal: object,
    *,
    policy: RuleBasedComputePolicy | None = None,
) -> ComputePolicyObservation:
    """Pure observer API. It has no runtime side effects and no execution authority."""

    classifier = policy or RuleBasedComputePolicy()
    return classifier.classify(budget_signal)


def observe_shadow_compute_if_enabled(
    budget_signal: object,
    *,
    flags: ComputePolicyShadowFlags,
    policy: RuleBasedComputePolicy | None = None,
) -> ComputePolicyObservation | None:
    """Return a shadow observation only when explicitly enabled in isolated M27."""

    if not flags.enabled:
        return None
    return classify_shadow_compute(budget_signal, policy=policy)
