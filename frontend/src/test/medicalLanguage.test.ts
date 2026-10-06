/**
 * AUDIT 18 -- Medical language audit (frontend companion).
 *
 * Repository-wide scan of frontend/src for prohibited medical/clinical
 * language, mirroring tests/audit/test_audit_medical_language.py on the
 * Python side. Runs under vitest (environment: "jsdom" per
 * vite.config.ts), but jsdom only simulates browser DOM globals inside
 * the same Node process -- Node's own `fs`/`path` modules remain fully
 * available at module scope in a .test.ts file, so this file needs no
 * special test-environment override.
 *
 * Excludes this file's own directory (frontend/src/test/) and any
 * __tests__ directories: those legitimately reference the blocked
 * phrases as *expected-absent* test assertions/fixtures, never as
 * display text.
 */

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const FRONTEND_SRC = path.resolve(__dirname, "..");

const EXCLUDE_DIR_NAMES = new Set(["test", "__tests__", "node_modules", "dist", "build"]);

// Same blocklist strategy as the backend audit test: specific
// multi-word phrases / anchored patterns, not bare single words like
// "disorder" or "diagnos" that appear legitimately in negated
// disclaimer sentences (see app/safety/messages.py PROHIBITED_PHRASES
// and its accompanying comment for the rationale this mirrors).
const BLOCKLIST_PATTERNS: RegExp[] = [
  /you have (dswpd|non-24|a circadian rhythm disorder|delayed sleep)/i,
  /you are diagnosed/i,
  /diagnosed with/i,
  /we diagnose/i,
  /this diagnoses/i,
  /clinical dlmo/i,
  /measured dlmo/i,
  /your exact dlmo/i,
  /laboratory dlmo/i,
  /your exact biological clock is/i,
  /this is a precise measurement/i,
  /your melatonin level is/i,
  /your clinical dlmo is/i,
  /take melatonin/i,
  /melatonin dose/i,
  /melatonin dosage/i,
  /\d+\s?mg of melatonin/i,
  /prescri(be|ption|bed)/i,
  /replaces a sleep study/i,
  /instead of seeing a doctor/i,
  /instead of a doctor/i,
  /in place of a doctor/i,
  /no need to see a doctor/i,
  /accuracy in humans/i,
  /clinically validated accuracy/i,
  /fda[- ]?(approved|cleared)/i,
];

function stripComments(text: string): string {
  // Blank out /* */ and // comments (equal-length blanking, newlines
  // preserved) so a comment *documenting* a prohibited phrase (e.g.
  // "never show 'Clinical DLMO'") doesn't trip the scan, matching the
  // Python-side test's rationale.
  const blank = (s: string) => s.replace(/[^\n]/g, " ");
  let out = text.replace(/\/\*[\s\S]*?\*\//g, blank);
  out = out.replace(/\/\/[^\n]*/g, blank);
  return out;
}

function walk(dir: string): string[] {
  const results: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (EXCLUDE_DIR_NAMES.has(entry.name)) continue;
      results.push(...walk(path.join(dir, entry.name)));
    } else if (entry.isFile() && /\.tsx?$/.test(entry.name)) {
      results.push(path.join(dir, entry.name));
    }
  }
  return results;
}

interface Violation {
  file: string;
  line: number;
  pattern: string;
  text: string;
}

function scan(files: string[]): Violation[] {
  const violations: Violation[] = [];
  for (const file of files) {
    const raw = fs.readFileSync(file, "utf-8");
    const display = stripComments(raw);
    const lines = raw.split("\n");
    for (const pattern of BLOCKLIST_PATTERNS) {
      const global = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g");
      let match: RegExpExecArray | null;
      while ((match = global.exec(display)) !== null) {
        const lineNo = display.slice(0, match.index).split("\n").length;
        violations.push({
          file,
          line: lineNo,
          pattern: pattern.source,
          text: (lines[lineNo - 1] ?? "").trim(),
        });
      }
    }
  }
  return violations;
}

describe("AUDIT 18 -- medical language scan (frontend/src)", () => {
  it("contains no prohibited medical/clinical language in participant-facing source", () => {
    const files = walk(FRONTEND_SRC);
    const violations = scan(files);
    const message = violations
      .map((v) => `${v.file}:${v.line}  [pattern=${v.pattern}]  ${v.text}`)
      .join("\n");
    expect(violations, `Prohibited medical/clinical language found:\n${message}`).toHaveLength(0);
  });

  it("keeps the approved wellness-boundary terminology intact", () => {
    const messagesTs = fs.readFileSync(path.join(FRONTEND_SRC, "utils", "messages.ts"), "utf-8");
    const terminologyTs = fs.readFileSync(path.join(FRONTEND_SRC, "utils", "terminology.ts"), "utf-8");

    expect(messagesTs).toContain('export const NON_DIAGNOSTIC_STATEMENT = "This is not a diagnosis.";');
    expect(messagesTs).toContain(
      "CircadianIQ estimates your circadian phase from behavioral patterns. It is not a medical device, does not perform laboratory measurements, and does not diagnose any condition."
    );
    expect(messagesTs).toContain(
      'export const HIGH_SEVERITY_BODY = "CircadianIQ cannot diagnose circadian rhythm disorders.";'
    );
    expect(messagesTs).toContain('moderate: "Estimated from partial data."');

    expect(terminologyTs).toContain('MODERATE: "Pattern note"');
    expect(terminologyTs).toContain('HIGH: "Safety note"');
  });
});
