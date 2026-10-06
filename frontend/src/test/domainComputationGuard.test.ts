import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Architectural guard: the UI must only *format/display* values the
 * API already computed (DLMO, alignment, confidence, contributor,
 * safety, recommendation numbers) -- it must never derive one of
 * those domain values itself from raw inputs. This is inherently
 * heuristic (see AUDIT 20 step 2): we grep for arithmetic operators
 * near domain-sounding identifiers, then hand-classify each hit as
 * legitimate formatting/layout math or a genuine violation. Only
 * genuine violations fail the test.
 *
 * Reviewed and confirmed BENIGN (documented so a future run doesn't
 * need to re-derive the same reasoning):
 *  - AlignmentBreakdown.tsx: `Math.max(2, Math.min(100, value))` and
 *    `Math.round(value)` -- clamping/rounding an already-final
 *    component score for bar width / display, not deriving it.
 *  - ContributorCard.tsx: `Math.abs(Math.round(contributor.effect_minutes))`
 *    and `Math.round(contributor.alignment_deficit)` /
 *    `Math.round(contributor.contributor_score)` -- formatting
 *    already-final API numbers.
 *  - RecommendationCard.tsx: `Math.abs(Math.round(primary.expected_improvement_minutes))`
 *    -- formatting only.
 *  - InterventionProgress.tsx: `compliant.length / observed.length`
 *    rendered as "X / Y days followed" -- this is a *display* of two
 *    counts as a fraction pair (literal text "compliant / observed"),
 *    not an arithmetic division producing a new domain score; no
 *    division operator is evaluated (`/` appears only inside JSX
 *    text as literal punctuation between two counts). Confirmed by
 *    reading the JSX: `{compliant.length} / {observed.length}` are
 *    two sibling expressions, not `compliant.length / observed.length`.
 *  - TrajectoryChart.tsx: `(value - min) / span`, `padding + (index / ...) * (width - padding * 2)`,
 *    `height - padding - ((value - min) / span) * (height - padding * 2)`
 *    -- SVG pixel-coordinate geometry for plotting already-fetched
 *    values on a chart; it repositions points in *pixel space*, it
 *    does not alter or derive the plotted domain values themselves
 *    (`value` always comes from `parseClockHour`/`alignment_score`/
 *    `confidence_score` fields returned by the API, unwrapped only
 *    for continuous-line rendering per utils/time.ts).
 *  - ClockVisualization.tsx: trig placement of markers
 *    (`radius * Math.cos(angle)`, etc.) -- pixel geometry from an
 *    API-supplied HH:MM string via parseClockHour/hourToDegrees, not
 *    a new domain value.
 *  - ConfidenceBadge.tsx: `Math.round(confidence.score)` -- formatting.
 *  - BiologicalClockCard.tsx: no arithmetic on domain values (only
 *    string interpolation of the API's own value).
 *
 * No genuinely suspicious computation (deriving DLMO, alignment,
 * confidence, contributor, or safety-threshold values from raw
 * component/observation data) was found in any component checked.
 */

const __dirname = dirname(fileURLToPath(import.meta.url));

const FILES_TO_CHECK = [
  "../components/AlignmentBreakdown.tsx",
  "../components/AlignmentScore.tsx",
  "../components/ContributorsList.tsx",
  "../components/ContributorCard.tsx",
  "../components/RecommendationCard.tsx",
  "../components/NudgeCard.tsx",
  "../components/SafetyBanner.tsx",
  "../components/ClockVisualization.tsx",
  "../components/ConfidenceBadge.tsx",
  "../components/BiologicalClockCard.tsx",
  "../components/InterventionProgress.tsx",
  "../components/TrajectoryChart.tsx",
  "../pages/Dashboard.tsx",
];

// Domain-sounding identifiers: if an arithmetic operator appears on a
// (code, not string/comment) line mentioning one of these, the line
// is a "hit" requiring manual review (see the module doc comment
// above for the review record).
const DOMAIN_TERMS = /(dlmo|alignment|confidence|contributor|threshold|severity|safety|recommendation|effect_minutes|compliance)/i;

// An arithmetic operator sitting between two code tokens (identifier,
// number, closing paren/bracket on one side; identifier, number,
// opening paren on the other). Applied only to `code` after string
// literals, JSX text, comments and import/export lines are stripped
// out below, so CSS custom-property names ("--color-...") and
// relative import paths ("../api/types") never match.
const ARITHMETIC_OPERATOR = /[a-zA-Z0-9_.\])][ ]?[-+*/%][ ]?[a-zA-Z0-9_.(]/;

// Lines that are allowed to contain arithmetic near a domain term
// because they are known-benign (documented above). Anything NOT
// matching one of these on a flagged line is a real failure.
const BENIGN_LINE_PATTERNS = [
  /Math\.round\(/,
  /Math\.max\(/,
  /Math\.min\(/,
  /Math\.abs\(/,
  /Math\.cos\(/,
  /Math\.sin\(/,
  /padding/, // SVG layout geometry
  /width\s*-|height\s*-|radius\s*\*/, // SVG layout geometry
  /compliant\.length.*observed\.length/, // JSX text fraction, not a division
  /gap|marginTop|fontSize|borderWidth/, // CSS values
];

/** Strips string/template literals, JSX attribute string values, and
 * comments from a source line so arithmetic-operator detection only
 * looks at actual executable code -- not at "--color-...", "../api/types",
 * or English prose that happens to contain a hyphen or slash. This is
 * intentionally crude (no real JS parser), matching the heuristic,
 * hand-reviewed nature of this guard. */
function stripNonCode(line: string): string {
  let code = line;
  code = code.replace(/\/\*.*?\*\//g, ""); // inline block comments
  if (/^\s*(\*|\/\/|\/\*)/.test(code)) return ""; // whole-line comments (JSDoc etc.)
  if (/^\s*(import|export)\b/.test(code)) return ""; // import/export statements
  code = code.replace(/`(?:[^`\\]|\\.)*`/g, "``"); // template literals
  code = code.replace(/"(?:[^"\\]|\\.)*"/g, '""'); // double-quoted strings
  code = code.replace(/'(?:[^'\\]|\\.)*'/g, "''"); // single-quoted strings
  code = code.replace(/\/\/.*$/, ""); // trailing line comments
  return code;
}

describe("Architectural guard: UI never computes domain values", () => {
  it("has no suspicious arithmetic deriving domain values from raw inputs", () => {
    const violations: string[] = [];
    const reviewedHits: string[] = [];

    for (const relPath of FILES_TO_CHECK) {
      const absPath = resolve(__dirname, relPath);
      const content = readFileSync(absPath, "utf-8");
      const lines = content.split("\n");

      lines.forEach((line: string, idx: number) => {
        const code = stripNonCode(line);
        if (!code) return;
        if (!DOMAIN_TERMS.test(code)) return;
        if (!ARITHMETIC_OPERATOR.test(code)) return;

        const hitDescription = `${relPath}:${idx + 1}: ${line.trim()}`;
        const isBenign = BENIGN_LINE_PATTERNS.some((p) => p.test(line));
        if (isBenign) {
          reviewedHits.push(hitDescription);
        } else {
          violations.push(hitDescription);
        }
      });
    }

    // Documented evidence this test actually inspected something,
    // rather than vacuously passing because no domain terms matched.
    expect(reviewedHits.length).toBeGreaterThan(0);

    if (violations.length > 0) {
      throw new Error(
        `Found ${violations.length} line(s) with arithmetic near domain-sounding identifiers that are ` +
          `NOT in the reviewed-benign list. Manually classify each: is it genuinely deriving a domain ` +
          `value (DLMO, alignment, confidence, contributor score, safety threshold) from raw data, or ` +
          `just formatting/layout? If benign, add it to BENIGN_LINE_PATTERNS with justification in the ` +
          `module doc comment. Violations:\n${violations.join("\n")}`,
      );
    }
  });
});
