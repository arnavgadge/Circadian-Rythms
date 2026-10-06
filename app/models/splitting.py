"""Deterministic participant-level train/test splitting.

The split is performed on **participant IDs**, never on rows: every
window belonging to a participant goes to whichever side that
participant was assigned to, so a participant can never appear in both
the training and test sets. This is the single most important
leakage guard in this phase.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class SplitResult:
    train_ids: tuple
    test_ids: tuple
    seed: int
    test_fraction: float
    split_version: str

    def to_json_dict(self) -> dict:
        d = asdict(self)
        d["train_ids"] = list(self.train_ids)
        d["test_ids"] = list(self.test_ids)
        return d

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.to_json_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "SplitResult":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            train_ids=tuple(data["train_ids"]),
            test_ids=tuple(data["test_ids"]),
            seed=data["seed"],
            test_fraction=data["test_fraction"],
            split_version=data["split_version"],
        )


def split_participants(
    participant_ids: Sequence[int],
    test_fraction: float,
    seed: int,
    split_version: str = "v1",
) -> SplitResult:
    """Deterministically split ``participant_ids`` into train/test sets.

    Same ``participant_ids`` + ``test_fraction`` + ``seed`` always
    produces the identical split (a fixed-seed shuffle, not a random
    draw), so the test set can be reproduced exactly from configuration
    alone -- see :class:`SplitResult` for the metadata this also lets
    callers persist.
    """

    if not 0.0 < test_fraction < 1.0:
        raise ValueError(f"test_fraction must be in (0, 1), got {test_fraction}")

    ids = sorted(set(participant_ids))
    n = len(ids)
    n_test = round(n * test_fraction)

    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(ids)

    test_ids = tuple(sorted(int(i) for i in shuffled[:n_test]))
    train_ids = tuple(sorted(int(i) for i in shuffled[n_test:]))

    assert set(train_ids).isdisjoint(test_ids), "train/test participant sets must not overlap"
    assert len(train_ids) + len(test_ids) == n

    return SplitResult(
        train_ids=train_ids,
        test_ids=test_ids,
        seed=seed,
        test_fraction=test_fraction,
        split_version=split_version,
    )
