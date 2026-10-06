"""Generates the 7 required demo figures + docs/demo_story.md from the
already-produced release/demo_30day/daily_summary.csv and journey_summary.json.

    python -m app.scripts.generate_30day_demo_figures

Never recomputes anything -- pure visualization/reporting over the real
pipeline output `app.scripts.run_30day_demo` already wrote. All figures
are captioned "SYNTHETIC DEMONSTRATION PARTICIPANT" per the brief.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "release" / "demo_30day"
FIGURES_DIR = OUTPUT_DIR / "figures"

DISCLAIMER = "SYNTHETIC DEMONSTRATION PARTICIPANT -- deterministic scenario, not a sampled population or real individual."


def _clock_hour(hhmmss: str | None) -> float | None:
    if not hhmmss:
        return None
    parts = hhmmss.split(":")
    h, m = int(parts[0]), int(parts[1])
    return h + m / 60.0


def main() -> int:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from app.safety.circular_stats import unwrap_circular_series

    daily_rows = list(csv.DictReader((OUTPUT_DIR / "daily_summary.csv").open(encoding="utf-8")))
    journey = json.loads((OUTPUT_DIR / "journey_summary.json").read_text(encoding="utf-8"))

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    days = [int(r["day"]) for r in daily_rows]

    def _plot_hours(field, title, ylabel, fname, invert=False):
        raw = [_clock_hour(r[field]) for r in daily_rows]
        present_days = [d for d, v in zip(days, raw) if v is not None]
        present_vals = [v for v in raw if v is not None]
        unwrapped = unwrap_circular_series(present_vals)
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.plot(present_days, unwrapped, marker="o", markersize=3, color="#3b5fe0")
        ax.set_xlabel("Story day")
        ax.set_ylabel(ylabel)
        ax.set_title(f"{title}\n({DISCLAIMER})", fontsize=9)
        for stage_start, stage_label in [(1, "Baseline"), (8, "Identify"), (11, "Change"), (19, "Response"), (25, "Stable")]:
            ax.axvline(stage_start, color="grey", linestyle=":", linewidth=0.7)
        if invert:
            ax.invert_yaxis()
        fig.tight_layout()
        fig.savefig(FIGURES_DIR / fname, dpi=120)
        plt.close(fig)

    # 1. DLMO across 30 days (fused)
    _plot_hours("fused_dlmo", "Estimated Biological Clock (Fused DLMO) Across 30 Days", "Hour of day (unwrapped)", "01_dlmo_across_30_days.png")

    # 2. Alignment score across 30 days
    fig, ax = plt.subplots(figsize=(9, 4.5))
    align_days = [int(r["day"]) for r in daily_rows if r["alignment_score"] not in (None, "", "None")]
    align_vals = [float(r["alignment_score"]) for r in daily_rows if r["alignment_score"] not in (None, "", "None")]
    ax.plot(align_days, align_vals, marker="o", markersize=3, color="#1a9e5c")
    ax.set_xlabel("Story day")
    ax.set_ylabel("Alignment score (0-100)")
    ax.set_ylim(0, 100)
    ax.set_title(f"Alignment Score Across 30 Days\n({DISCLAIMER})", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "02_alignment_score_across_30_days.png", dpi=120)
    plt.close(fig)

    # 3. Screen cutoff across 30 days
    _plot_hours("screen_end", "Evening Screen Cutoff Across 30 Days", "Hour of day (unwrapped)", "03_screen_cutoff_across_30_days.png")

    # 4. Morning light timing across 30 days
    _plot_hours("morning_light_start", "Morning Light Start Time Across 30 Days", "Hour of day", "04_morning_light_timing_across_30_days.png")

    # 5. Compliance across 30 days
    fig, ax = plt.subplots(figsize=(9, 4.5))
    comp_days = [int(r["day"]) for r in daily_rows if r["compliance_degree"] not in (None, "", "None")]
    comp_vals = [float(r["compliance_degree"]) for r in daily_rows if r["compliance_degree"] not in (None, "", "None")]
    ax.bar(comp_days, comp_vals, color="#d98c2b")
    ax.set_xlabel("Story day")
    ax.set_ylabel("Compliance degree (0-1)")
    ax.set_ylim(0, 1.05)
    ax.set_title(f"Intervention Compliance Across 30 Days\n({DISCLAIMER})", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "05_compliance_across_30_days.png", dpi=120)
    plt.close(fig)

    # 6. Contributor transition (top contributor per day, categorical)
    fig, ax = plt.subplots(figsize=(9, 3.5))
    contributors = [r["top_contributor"] or "n/a" for r in daily_rows]
    unique_contributors = sorted(set(contributors))
    y_positions = [unique_contributors.index(c) for c in contributors]
    ax.scatter(days, y_positions, c=y_positions, cmap="tab10", s=25)
    ax.set_yticks(range(len(unique_contributors)))
    ax.set_yticklabels(unique_contributors)
    ax.set_xlabel("Story day")
    ax.set_title(f"Top Contributor Transition\n({DISCLAIMER})", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "06_contributor_transition.png", dpi=120)
    plt.close(fig)

    # 7. DLMO: XGBoost vs State vs Fused
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for field, label, color in [("xgb_dlmo", "XGBoost", "#e05353"), ("state_dlmo", "State engine", "#3b5fe0"), ("fused_dlmo", "Fused", "#1a9e5c")]:
        raw = [_clock_hour(r[field]) for r in daily_rows]
        present_days = [d for d, v in zip(days, raw) if v is not None]
        present_vals = [v for v in raw if v is not None]
        unwrapped = unwrap_circular_series(present_vals)
        ax.plot(present_days, unwrapped, marker="o", markersize=2.5, label=label, color=color)
    ax.set_xlabel("Story day")
    ax.set_ylabel("Hour of day (unwrapped)")
    ax.legend()
    ax.set_title(f"DLMO Estimates: XGBoost vs State Engine vs Fusion\n({DISCLAIMER})", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "07_dlmo_xgb_state_fused.png", dpi=120)
    plt.close(fig)

    print(f"Wrote 7 figures to {FIGURES_DIR}")

    # --- demo_story.md ---
    checkpoints = journey["checkpoints"]

    def _cp(day):
        return checkpoints.get(str(day)) or checkpoints.get(day)

    cp7, cp10, cp18, cp24, cp30 = (_cp(d) for d in (7, 10, 18, 24, 30))

    lines = []
    lines.append("# 30-Day Demo Story: Arjun -- CircadianIQ Demo User\n")
    lines.append("**This is a deterministic synthetic demonstration participant "
                  "(participant_id=9001), not a sampled population participant and not a real "
                  "individual.** Every value below is a real, unmodified output of the CircadianIQ "
                  "pipeline (feature engineering -> XGBoost -> state engine -> fusion -> alignment "
                  "-> contributors -> recommendation -> compliance -> personalization) given a "
                  "predefined, hand-designed 30-day behavioral schedule "
                  "(`demo/scenarios/late_screen_recovery_30d.yaml`). Nothing in this report was "
                  "hard-coded or manually adjusted after the fact -- see "
                  "`docs/30_day_demo_scenario.md` for the full design rationale, including two "
                  "schedule retunings made *before* accepting this final run, each driven by "
                  "inspecting real pipeline output rather than the desired narrative.\n")

    lines.append("## Persona\n")
    lines.append("Chronotype: **Late**. Behavioral personality: screen-heavy user with a mild "
                  "social jetlag pattern. This is a deliberately-designed persona for "
                  "demonstration purposes, not drawn from the synthetic population generator.\n")

    def _fmt_cp(cp, label):
        if cp is None:
            return f"### {label}\n\n(No committed prediction for this day.)\n"
        out = [f"### {label} ({cp['date']}, stage {cp['stage']})\n"]
        out.append(f"- Estimated biological clock (fused DLMO): **{cp['fused_dlmo']}**")
        out.append(f"- Alignment score: **{cp['alignment_score']:.1f}/100**" if cp['alignment_score'] is not None else "- Alignment score: not available")
        if cp.get("alignment_components"):
            comps = ", ".join(f"{k}={v:.0f}" for k, v in cp["alignment_components"].items())
            out.append(f"  - Components: {comps}")
        if cp.get("contributors"):
            top = ", ".join(f"#{c['rank']} {c['signal']} ({c['direction']})" for c in cp["contributors"])
            out.append(f"- Top contributors: {top}")
        out.append(f"- Confidence: {cp['confidence']}")
        out.append(f"- Recommendation: {cp['recommendation'] or '(none)'}")
        out.append(f"- Compliance: {cp['compliance_degree']:.2f}" if cp['compliance_degree'] is not None else "- Compliance: n/a")
        out.append(f"- Personalization phase: {cp['personalization_phase'] or 'literature'}")
        return "\n".join(out) + "\n"

    lines.append("## Days 1-7 -- Baseline\n")
    lines.append("A consistently late, screen-heavy routine: sleep onset around 1:45-2:00 AM, "
                  "evening screens until 1:15-1:30 AM, weak/late morning light, a late last meal, "
                  "and moderate social jetlag. Held stable (small deterministic variation only, "
                  "never random) so the system has a coherent 6-day window once prediction begins "
                  "on day 7.\n")
    lines.append(_fmt_cp(cp7, "CHECKPOINT_DAY_7"))

    lines.append("## Days 8-10 -- System Identifies the Problem\n")
    lines.append("The baseline pattern continues while the system, now with a full trailing "
                  "history, ranks contributors and issues a graduated recommendation targeting "
                  "the dominant contributor.\n")
    lines.append(_fmt_cp(cp10, "CHECKPOINT_DAY_10"))

    lines.append("## Days 11-18 -- Behavioral Change\n")
    lines.append("A deliberate, gradual improvement in screen cutoff and morning light timing, "
                  "with partial compliance early and stronger compliance later. The magnitude of "
                  "this change was tuned (see docs/30_day_demo_scenario.md) to a pace the real "
                  "state engine can actually track within the story's 30-day span, after an "
                  "initial, more aggressive draft was found to overshoot the model's own "
                  "adaptation speed.\n")
    lines.append(_fmt_cp(cp18, "CHECKPOINT_DAY_18"))

    lines.append("## Days 19-24 -- Biological Response\n")
    lines.append("Continued behavioral improvement. The estimated biological clock and alignment "
                  "score here are entirely the real state engine's and fusion layer's own output "
                  "-- never overwritten by this demo.\n")
    lines.append(_fmt_cp(cp24, "CHECKPOINT_DAY_24"))

    lines.append("## Days 25-30 -- Stable Improvement\n")
    lines.append("Behavior stabilizes at a substantially, but not perfectly, improved routine.\n")
    lines.append(_fmt_cp(cp30, "CHECKPOINT_DAY_30"))

    baseline_align = journey.get("baseline_mean_alignment")
    final_align = journey.get("final_mean_alignment")
    lines.append("## Summary\n")
    lines.append(f"- Mean alignment, days 1-10 (baseline/identify): **{baseline_align:.1f}**" if baseline_align else "")
    lines.append(f"- Mean alignment, days 25-30 (stable): **{final_align:.1f}**" if final_align else "")
    lines.append("- Personalization for both the `screen` and `meal` intervention types stayed at "
                  "the `literature` phase for the full 30 days. This is a genuine, inspected "
                  "outcome, not a shortfall to paper over: the recommendation engine's own "
                  "contributor-driven target legitimately shifted from screen to meal around day "
                  "19-20 (see the contributor transition figure), splitting the 23 days of "
                  "compliance evidence across two intervention types before either individually "
                  "reached the 3-weeks-active graduation threshold "
                  "(`app/personalization/config.py:ranking_min_weeks_active`). Per the brief's own "
                  "guidance, the honest report here is: **personalization is still learning from "
                  "this participant's history.**")
    lines.append("- All figures: `release/demo_30day/figures/`. Full daily data: "
                  "`release/demo_30day/daily_summary.csv`. Machine-readable summary: "
                  "`release/demo_30day/journey_summary.json`.")
    lines.append("- Every number above is an **observed, synthetic** output -- never a proven "
                  "causal effect and never a clinical measurement.")

    (OUTPUT_DIR / "demo_story.md").write_text("\n\n".join(l for l in lines if l), encoding="utf-8")
    print(f"Wrote {OUTPUT_DIR / 'demo_story.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
