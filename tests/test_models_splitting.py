"""Tests for participant-level train/test splitting."""

from __future__ import annotations

import pytest

from app.models.splitting import SplitResult, split_participants


def test_split_produces_expected_sizes_for_1000_participants():
    ids = list(range(1, 1001))
    split = split_participants(ids, test_fraction=0.2, seed=2025)
    assert len(split.train_ids) == 800
    assert len(split.test_ids) == 200


def test_split_has_zero_participant_overlap():
    ids = list(range(1, 1001))
    split = split_participants(ids, test_fraction=0.2, seed=2025)
    assert set(split.train_ids).isdisjoint(set(split.test_ids))
    assert set(split.train_ids) | set(split.test_ids) == set(ids)


def test_split_is_deterministic_given_same_seed():
    ids = list(range(1, 501))
    split1 = split_participants(ids, test_fraction=0.2, seed=99)
    split2 = split_participants(ids, test_fraction=0.2, seed=99)
    assert split1.train_ids == split2.train_ids
    assert split1.test_ids == split2.test_ids


def test_different_seeds_produce_different_splits():
    ids = list(range(1, 501))
    split1 = split_participants(ids, test_fraction=0.2, seed=1)
    split2 = split_participants(ids, test_fraction=0.2, seed=2)
    assert split1.test_ids != split2.test_ids


def test_split_rejects_invalid_test_fraction():
    with pytest.raises(ValueError):
        split_participants([1, 2, 3], test_fraction=1.5, seed=1)
    with pytest.raises(ValueError):
        split_participants([1, 2, 3], test_fraction=0.0, seed=1)


def test_split_result_round_trips_through_json(tmp_path):
    ids = list(range(1, 51))
    split = split_participants(ids, test_fraction=0.2, seed=7, split_version="v1")
    path = tmp_path / "split.json"
    split.save(path)

    loaded = SplitResult.load(path)
    assert loaded.train_ids == split.train_ids
    assert loaded.test_ids == split.test_ids
    assert loaded.seed == split.seed
    assert loaded.split_version == split.split_version
