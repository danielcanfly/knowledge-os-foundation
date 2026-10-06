from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

LOW_MEMORY_MIN_AVAILABLE_MB = 192
LOW_MEMORY_MAX_SWAP_USED_MB = 768
EVAL_LABEL_KEY = "com.daniel.m27.eval"
EVAL_LABEL_VALUE = "true"
EVAL_NAME_PREFIX = "m27-isolated-eval-"
PROTECTED_NAMES = {"llm_wiki-knowledge-engine-1", "knowledge-engine-test-answers"}


@dataclass(frozen=True, slots=True)
class ContainerRecord:
    name: str
    labels: Mapping[str, str]


def is_eval_container(record: ContainerRecord) -> bool:
    return (
        record.name.startswith(EVAL_NAME_PREFIX)
        and record.labels.get(EVAL_LABEL_KEY) == EVAL_LABEL_VALUE
    )


def eval_container_count(records: Sequence[ContainerRecord]) -> int:
    return sum(1 for record in records if is_eval_container(record))


def exactly_one_eval_container(records: Sequence[ContainerRecord]) -> bool:
    return eval_container_count(records) == 1


def cleanup_allowed(record: ContainerRecord) -> bool:
    return record.name not in PROTECTED_NAMES and is_eval_container(record)


def low_memory_guard_passes(*, available_memory_mb: int, swap_used_mb: int) -> bool:
    return (
        available_memory_mb >= LOW_MEMORY_MIN_AVAILABLE_MB
        and swap_used_mb <= LOW_MEMORY_MAX_SWAP_USED_MB
    )
