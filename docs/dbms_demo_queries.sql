-- ============================================================================
-- CircadianIQ -- DBMS Demo Queries (Phase 18 release)
-- ============================================================================
-- Read-only (SELECT-only) queries for a live walkthrough of the relational
-- schema against the seeded demo database, data/demo.db. All table and
-- column names below were read directly from docs/final_database_design.md
-- (the current, authoritative schema reference, Alembic head e5f9c27b4d8a)
-- and cross-checked against docs/database_architecture.md; nothing here is
-- invented. No INSERT/UPDATE/DELETE/DROP statements appear in this file.
--
-- Run against the demo database from a shell in the repository root:
--     sqlite3 data/demo.db < docs/dbms_demo_queries.sql
-- or open `sqlite3 data/demo.db` interactively and paste one query at a
-- time (recommended for a live audience -- see docs/demo_runbook.md,
-- step 13).
--
-- Demo participants referenced below (seeded by
-- `python -m app.scripts.seed_demo_scenarios`, seed=777 -- see
-- release/demo/demo_scenarios.json for the full disclosure):
--   1  = NORMAL                (confidence high, no safety flag)
--   3  = LOW_CONFIDENCE         (confidence moderate, no safety flag)
--   25 = MODERATE_SAFETY_FLAG   (safety active, severity MODERATE, recommendation NOT suppressed)
--   41 = HIGH_SAFETY_FLAG       (safety active, severity HIGH, recommendation IS suppressed;
--                                this participant's DLMO trajectory was directly authored,
--                                not emergent -- see demo_scenarios.json for the disclosure)
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 1. Identity + current state for the four demo participants
-- ----------------------------------------------------------------------------
-- Demonstrates: a 1:1 JOIN between an append-only identity table
-- (participants) and its mutable current-state counterpart
-- (participant_profiles), the normalization split described in
-- docs/final_database_design.md section 6.
SELECT
    p.id                            AS participant_id,
    p.participant_code,
    p.status,
    p.enrollment_date,
    pp.chronotype_category,
    pp.current_dlmo_time,
    pp.current_alignment_score,
    pp.meq_category
FROM participants p
JOIN participant_profiles pp ON pp.participant_id = p.id
WHERE p.id IN (1, 3, 25, 41)
ORDER BY p.id;


-- ----------------------------------------------------------------------------
-- 2. The is_latest event-sourcing pattern on circadian_labels (participant 1)
-- ----------------------------------------------------------------------------
-- Demonstrates: circadian_labels stores one row per PREDICTION EVENT, not
-- one row per date -- a date can accumulate multiple rows if inference is
-- ever re-run, and is_latest marks the single currently-authoritative row
-- without a window-function tiebreak (docs/final_database_design.md
-- section 4.5). The first query below counts every row ever written for
-- participant 1; the second shows only the "is_latest = 1" subset that the
-- API and UI actually read from.
SELECT
    COUNT(*)                                     AS total_circadian_label_rows,
    SUM(CASE WHEN is_latest = 1 THEN 1 ELSE 0 END) AS is_latest_rows
FROM circadian_labels
WHERE participant_id = 1;

SELECT
    target_date,
    fused_dlmo_time,
    confidence_label,
    confidence_score,
    is_latest,
    computed_at
FROM circadian_labels
WHERE participant_id = 1
  AND is_latest = 1
ORDER BY target_date DESC
LIMIT 10;


-- ----------------------------------------------------------------------------
-- 3. Alignment score + 5-component breakdown for participant 25's most
--    recent prediction
-- ----------------------------------------------------------------------------
-- Demonstrates: the 1:1 join from circadian_labels -> alignment_results
-- (final_alignment_score = 60% phase + 40% behavioral, computed in
-- Python, stored in SQL) exposing all five named behavioral sub-scores
-- as real, individually queryable columns rather than a single opaque
-- JSON blob.
SELECT
    cl.target_date,
    cl.fused_dlmo_time,
    ar.final_alignment_score,
    ar.phase_alignment_score,
    ar.behavioral_alignment_score,
    ar.sleep_consistency_score,
    ar.morning_light_score,
    ar.evening_screen_score,
    ar.meal_timing_score,
    ar.social_jetlag_score
FROM circadian_labels cl
JOIN alignment_results ar ON ar.circadian_label_id = cl.id
WHERE cl.participant_id = 25
  AND cl.is_latest = 1;


-- ----------------------------------------------------------------------------
-- 4. Ranked top contributors for participant 1's most recent prediction
-- ----------------------------------------------------------------------------
-- Demonstrates: alignment_results -> contributor_results (1:N), a
-- normalized top-N ranking (one row per rank) rather than a single
-- unstructured string, ordered by the schema's own `rank` column.
SELECT
    cl.target_date,
    cr.rank,
    cr.contributor_signal,
    cr.direction,
    cr.contributor_score,
    cr.today_anomaly
FROM circadian_labels cl
JOIN alignment_results ar ON ar.circadian_label_id = cl.id
JOIN contributor_results cr ON cr.alignment_result_id = ar.id
WHERE cl.participant_id = 1
  AND cl.is_latest = 1
ORDER BY cr.rank;


-- ----------------------------------------------------------------------------
-- 5. Safety flags side by side: participant 25 (MODERATE) vs.
--    participant 41 (HIGH)
-- ----------------------------------------------------------------------------
-- Demonstrates: safety_flags as the audit trail behind the dashboard's
-- safety UI -- severity and recommendation_suppressed are real columns,
-- not something recomputed at display time. Participant 25's MODERATE
-- flag leaves recommendation_suppressed = 0 (a "Pattern note" is shown
-- alongside the recommendation); participant 41's HIGH flag has
-- recommendation_suppressed = 1 (the recommendation is withheld
-- entirely) -- see docs/demo_runbook.md step 12 for how this is shown live.
SELECT
    p.id                          AS participant_id,
    p.participant_code,
    sf.flag_type,
    sf.severity,
    sf.flagged_date,
    sf.recommendation_suppressed,
    sf.message_shown,
    sf.resolved_date
FROM safety_flags sf
JOIN participants p ON p.id = sf.participant_id
WHERE sf.participant_id IN (25, 41)
ORDER BY sf.participant_id, sf.flagged_date DESC;


-- ----------------------------------------------------------------------------
-- 6. Intervention history for participant 25
-- ----------------------------------------------------------------------------
-- Demonstrates: intervention_log as an append-only per-day outcome
-- record, joined to its catalogue entry in recommendations (the
-- normalization decision that keeps intervention_type/description in
-- exactly one place rather than repeated on every log row).
SELECT
    il.log_date,
    r.intervention_type,
    r.title,
    il.recommendation_text,
    il.compliance_binary,
    il.compliance_degree,
    il.dlmo_before_time,
    il.dlmo_after_time,
    il.alignment_change
FROM intervention_log il
JOIN recommendations r ON r.id = il.recommendation_id
WHERE il.participant_id = 25
ORDER BY il.log_date DESC
LIMIT 15;


-- ----------------------------------------------------------------------------
-- 7. Referential integrity: recommendations -> intervention_log
--    (a catalogue entry cannot be deleted while history references it)
-- ----------------------------------------------------------------------------
-- Demonstrates: the RESTRICT foreign key from intervention_log.recommendation_id
-- to recommendations.id (docs/final_database_design.md section 5) --
-- shown here as a read-only count of how many history rows currently
-- depend on each catalogue entry, i.e. exactly the set of rows that
-- would block a DELETE on recommendations if one were attempted.
SELECT
    r.id                    AS recommendation_id,
    r.intervention_code,
    r.intervention_type,
    r.is_active,
    COUNT(il.id)            AS n_intervention_log_rows_referencing_it
FROM recommendations r
LEFT JOIN intervention_log il ON il.recommendation_id = r.id
GROUP BY r.id, r.intervention_code, r.intervention_type, r.is_active
ORDER BY n_intervention_log_rows_referencing_it DESC;


-- ----------------------------------------------------------------------------
-- 8. Confidence + data completeness across all four demo participants'
--    latest predictions
-- ----------------------------------------------------------------------------
-- Demonstrates: one query spanning all four demo scenarios at once,
-- reading circadian_labels.confidence_label/confidence_score/
-- data_completeness directly -- the values participants 1 and 3 were
-- specifically seeded to differ on (high vs. moderate confidence).
SELECT
    p.id                  AS participant_id,
    p.participant_code,
    cl.target_date,
    cl.confidence_label,
    cl.confidence_score,
    cl.data_completeness,
    cl.disagreement_minutes
FROM circadian_labels cl
JOIN participants p ON p.id = cl.participant_id
WHERE cl.participant_id IN (1, 3, 25, 41)
  AND cl.is_latest = 1
ORDER BY p.id;


-- ----------------------------------------------------------------------------
-- 9. Population-wide: average alignment score by chronotype
-- ----------------------------------------------------------------------------
-- Demonstrates: a GROUP BY aggregate across the whole participant
-- population (not scoped to the 4 demo IDs) -- the kind of query a
-- researcher would run to sanity-check the synthetic population's
-- behavior by cohort. Run this against a database with more than the
-- 4 demo participants (e.g. data/circadianiq.db after
-- generate_synthetic_data, or a larger --participants run of
-- seed_demo_scenarios) for a meaningful spread.
SELECT
    pp.chronotype_category,
    COUNT(DISTINCT p.id)              AS n_participants,
    ROUND(AVG(cl.confidence_score), 1) AS avg_confidence_score,
    ROUND(AVG(pp.current_alignment_score), 1) AS avg_current_alignment_score
FROM participants p
JOIN participant_profiles pp ON pp.participant_id = p.id
LEFT JOIN circadian_labels cl ON cl.participant_id = p.id AND cl.is_latest = 1
GROUP BY pp.chronotype_category
ORDER BY avg_current_alignment_score DESC;


-- ----------------------------------------------------------------------------
-- 10. Personalization phase distribution across participants
-- ----------------------------------------------------------------------------
-- Demonstrates: personal_effect_models as the persisted output of the
-- Phase 13 offline personalization-update pipeline -- one row per
-- (participant, intervention_type), never recomputed inline during
-- daily inference. Counts how many participant/intervention-type pairs
-- have reached each of the four personalization phases
-- (literature / personal_ranking / personal_effect / adaptive_policy).
-- NOTE: returns 0 rows against data/demo.db as seeded -- the demo
-- scenarios exercise behavioral history and daily inference, not the
-- separate intervention-logging/compliance cycle personalization needs
-- (see release/demo/demo_scenarios.json's "personalization_mature_scenario"
-- note). Run against a database with real intervention history for
-- non-empty results.
SELECT
    personalization_phase,
    intervention_type,
    COUNT(*)                       AS n_participant_intervention_pairs,
    ROUND(AVG(num_observations), 1) AS avg_observations,
    ROUND(AVG(r_squared), 3)        AS avg_r_squared
FROM personal_effect_models
GROUP BY personalization_phase, intervention_type
ORDER BY intervention_type, personalization_phase;


-- ----------------------------------------------------------------------------
-- 11. Intervention effectiveness outcomes by measurement phase
-- ----------------------------------------------------------------------------
-- Demonstrates: intervention_effect_estimates as an append-only,
-- never-overwritten log (a recomputation inserts a new row rather than
-- updating the old one -- see docs/intervention_effectiveness.md
-- "Recomputation"), and the three-tier measurement_phase methodology
-- (1 = observational, 2 = matched-observational, 3 =
-- regression-controlled) that keeps causal-strength labeling attached
-- to every individual estimate row rather than implied globally.
-- NOTE: also returns 0 rows against data/demo.db as seeded, for the
-- same reason as query 10 above -- no intervention-logging cycle was
-- run for the demo participants.
SELECT
    iee.measurement_phase,
    CASE iee.measurement_phase
        WHEN 1 THEN 'observational'
        WHEN 2 THEN 'matched_observational'
        WHEN 3 THEN 'regression_controlled'
    END                                       AS measurement_phase_label,
    r.intervention_type,
    COUNT(*)                                  AS n_estimates,
    ROUND(AVG(iee.effect_estimate), 1)        AS avg_effect_estimate_minutes,
    ROUND(AVG(iee.compliance_rate), 2)        AS avg_compliance_rate,
    ROUND(AVG(iee.n_observations), 1)         AS avg_n_observations
FROM intervention_effect_estimates iee
JOIN recommendations r ON r.id = iee.recommendation_id
GROUP BY iee.measurement_phase, r.intervention_type
ORDER BY iee.measurement_phase, r.intervention_type;


-- ----------------------------------------------------------------------------
-- 12. Full longitudinal history for one participant (multi-table join)
-- ----------------------------------------------------------------------------
-- Demonstrates: reconstructing a participant's complete day-by-day
-- story from four tables at once (behavioral observation -> predicted
-- DLMO -> alignment score -> top contributor), the "SQL as
-- authoritative longitudinal state" principle from
-- docs/final_database_design.md section 1 -- every one of these facts
-- lives in exactly one place and this query only reads, never derives.
SELECT
    do.observation_date,
    do.sleep_onset_time,
    do.evening_screen_duration_minutes,
    cl.fused_dlmo_time,
    cl.confidence_label,
    ar.final_alignment_score,
    (SELECT cr.contributor_signal FROM contributor_results cr
      WHERE cr.alignment_result_id = ar.id ORDER BY cr.rank ASC LIMIT 1) AS top_contributor
FROM daily_observations do
LEFT JOIN circadian_labels cl
    ON cl.participant_id = do.participant_id
   AND cl.target_date = do.observation_date
   AND cl.is_latest = 1
LEFT JOIN alignment_results ar ON ar.circadian_label_id = cl.id
WHERE do.participant_id = 25
ORDER BY do.observation_date ASC;


-- ----------------------------------------------------------------------------
-- 13. Training-run / model-version metadata history
-- ----------------------------------------------------------------------------
-- Demonstrates: training_runs as the queryable version-provenance table
-- for the one component that HAS structured provenance today (the
-- XGBoost model version) -- see docs/final_database_design.md's
-- discussion of known limitation #2 (most other component versions are
-- NOT similarly queryable; this query shows what full provenance
-- tracking would look like if it existed for every component).
SELECT
    id                AS training_run_id,
    model_type,
    model_version,
    num_participants,
    num_windows,
    feature_count,
    trained_at,
    artifact_path,
    artifact_version
FROM training_runs
ORDER BY trained_at DESC;
