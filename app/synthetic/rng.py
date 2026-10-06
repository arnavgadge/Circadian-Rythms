"""Reproducible, subsystem-separated random number generation.

A single global seed is split into independent named streams (one per
subsystem: population traits, personality assignment, daily behavior,
disruption events, biological-state noise, physiology). Each stream is
derived deterministically from the master seed via NumPy's
``SeedSequence.spawn``, so:

- the same master seed always reproduces the exact same dataset.
- changing, say, the physiology noise model does not perturb the
  random draws used for sleep-timing generation, because they come
  from different streams.
"""

from __future__ import annotations

import numpy as np

_STREAM_NAMES = (
    "population",
    "personality",
    "sensitivity",
    "behavior",
    "disruption",
    "state",
    "physiology",
)


class RandomStreams:
    """A named collection of independent, seed-reproducible ``Generator``s."""

    def __init__(self, seed: int) -> None:
        self._seed = seed
        root = np.random.SeedSequence(seed)
        child_seeds = root.spawn(len(_STREAM_NAMES))
        self._streams = {
            name: np.random.default_rng(child_seed)
            for name, child_seed in zip(_STREAM_NAMES, child_seeds)
        }

    @property
    def seed(self) -> int:
        return self._seed

    def __getitem__(self, name: str) -> np.random.Generator:
        try:
            return self._streams[name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown random stream '{name}'. Known streams: {sorted(self._streams)}"
            ) from exc

    def participant_stream(self, participant_index: int, name: str) -> np.random.Generator:
        """A per-participant sub-stream of ``name``, for participant-level draws
        that must not depend on the order participants happen to be processed in.

        Deterministic across processes: derived purely from the master
        seed plus two integers (the stream's fixed index and the
        participant's index), never from Python's randomized ``hash()``.
        """

        if name not in _STREAM_NAMES:
            raise KeyError(f"Unknown random stream '{name}'. Known streams: {list(_STREAM_NAMES)}")
        stream_index = _STREAM_NAMES.index(name)
        derived = np.random.SeedSequence(entropy=self._seed, spawn_key=(stream_index, participant_index))
        return np.random.default_rng(derived)
