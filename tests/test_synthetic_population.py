"""Tests for participant-level trait generation."""

from __future__ import annotations

from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC
from app.synthetic.population import CHRONOTYPES, generate_participants
from app.synthetic.rng import RandomStreams


def test_generate_participants_returns_requested_count():
    streams = RandomStreams(seed=1)
    participants = generate_participants(200, streams, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    assert len(participants) == 200


def test_chronotype_distribution_matches_configuration_exactly_at_n_1000():
    streams = RandomStreams(seed=7)
    participants = generate_participants(1000, streams, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    counts = {c: 0 for c in CHRONOTYPES}
    for p in participants:
        counts[p.chronotype] += 1

    expected = DEFAULT_SOURCE_BACKED.chronotype_population_proportions
    for chronotype, proportion in expected.items():
        assert counts[chronotype] == round(proportion * 1000)


def test_personality_distribution_matches_configuration_exactly_at_n_1000():
    streams = RandomStreams(seed=7)
    participants = generate_participants(1000, streams, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    counts: dict = {}
    for p in participants:
        counts[p.personality_key] = counts.get(p.personality_key, 0) + 1

    expected = DEFAULT_SYNTHETIC.personality_proportions
    for personality, proportion in expected.items():
        assert counts[personality] == round(proportion * 1000)


def test_meq_scores_within_instrument_range():
    streams = RandomStreams(seed=3)
    participants = generate_participants(300, streams, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    for p in participants:
        assert DEFAULT_SOURCE_BACKED.meq_score_min <= p.meq_score <= DEFAULT_SOURCE_BACKED.meq_score_max


def test_meq_trends_with_chronotype():
    streams = RandomStreams(seed=3)
    participants = generate_participants(300, streams, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    by_chronotype = {c: [] for c in CHRONOTYPES}
    for p in participants:
        by_chronotype[p.chronotype].append(p.meq_score)

    mean_early = sum(by_chronotype["early"]) / len(by_chronotype["early"])
    mean_late = sum(by_chronotype["late"]) / len(by_chronotype["late"])
    assert mean_early > mean_late


def test_sensitivities_are_clipped_to_configured_range():
    streams = RandomStreams(seed=9)
    participants = generate_participants(500, streams, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    low, high = DEFAULT_SYNTHETIC.sensitivity_clip_range
    for p in participants:
        assert low <= p.light_sensitivity <= high
        assert low <= p.screen_sensitivity <= high
        assert low <= p.meal_sensitivity <= high


def test_initial_adapted_and_current_dlmo_start_close_to_intrinsic():
    streams = RandomStreams(seed=11)
    participants = generate_participants(200, streams, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    from app.synthetic.time_utils import circular_diff_hours

    for p in participants:
        assert abs(circular_diff_hours(p.initial_adapted_dlmo_hour, p.intrinsic_dlmo_hour)) < 1.0
        assert abs(circular_diff_hours(p.initial_current_dlmo_hour, p.intrinsic_dlmo_hour)) < 1.0


def test_different_seeds_produce_different_populations():
    a = generate_participants(100, RandomStreams(seed=1), DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    b = generate_participants(100, RandomStreams(seed=2), DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    intrinsic_a = [p.intrinsic_dlmo_hour for p in a]
    intrinsic_b = [p.intrinsic_dlmo_hour for p in b]
    assert intrinsic_a != intrinsic_b


def test_same_seed_produces_identical_populations():
    a = generate_participants(100, RandomStreams(seed=42), DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    b = generate_participants(100, RandomStreams(seed=42), DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    for pa, pb in zip(a, b):
        assert pa == pb
