import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { CONTRAST_PAIRS, contrastRatio, parseColor } from "./contrast.ts";

// Reads the real tokens.css, resolves light-dark() and var() for each theme, and checks every pair the
// components render. A token edit that breaks WCAG AA fails here, not in a review screenshot.

const css = readFileSync(new URL("./tokens.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const tokens = new Map<string, string>();
for (const m of css.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
  if (!tokens.has(m[1] ?? "")) tokens.set(m[1] ?? "", (m[2] ?? "").trim()); // first (root) definition wins
}

function resolve(value: string, scheme: "light" | "dark", depth = 0): string {
  assert.ok(depth < 10, `token cycle at ${value}`);
  const ld = /^light-dark\((.+)\)$/.exec(value);
  if (ld) {
    const [light, dark] = splitTopLevel(ld[1] ?? "");
    return resolve((scheme === "light" ? light : dark) ?? "", scheme, depth + 1);
  }
  const v = /^var\((--[\w-]+)\)$/.exec(value);
  if (v) {
    const next = tokens.get(v[1] ?? "");
    assert.ok(next !== undefined, `unknown token ${v[1]}`);
    return resolve(next, scheme, depth + 1);
  }
  return value;
}

function splitTopLevel(s: string): string[] {
  let depth = 0;
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "(") depth++;
    else if (s[i] === ")") depth--;
    else if (s[i] === "," && depth === 0) return [s.slice(0, i).trim(), s.slice(i + 1).trim()];
  }
  return [s.trim()];
}

function color(token: string, scheme: "light" | "dark") {
  const raw = tokens.get(token);
  assert.ok(raw !== undefined, `unknown token ${token}`);
  const rgb = parseColor(resolve(raw, scheme));
  assert.ok(rgb, `${token} (${scheme}) is not a solid color`);
  return rgb;
}

test("parseColor reads hex and rgb() forms", () => {
  assert.deepEqual(parseColor("#fff"), [255, 255, 255]);
  assert.deepEqual(parseColor("#49685D"), [73, 104, 93]);
  assert.deepEqual(parseColor("rgb(36, 40, 36)"), [36, 40, 36]);
  assert.deepEqual(parseColor("rgb(36 40 36 / 0.5)"), [36, 40, 36]);
  assert.equal(parseColor("transparent"), null);
});

test("contrast ratio matches the WCAG reference values", () => {
  assert.equal(contrastRatio([0, 0, 0], [255, 255, 255]).toFixed(1), "21.0");
  assert.equal(contrastRatio([255, 255, 255], [255, 255, 255]), 1);
});

for (const scheme of ["light", "dark"] as const) {
  test(`every rendered color pair meets WCAG AA in the ${scheme} theme`, () => {
    const failures = CONTRAST_PAIRS.map((p) => ({ ...p, ratio: contrastRatio(color(p.fg, scheme), color(p.bg, scheme)) }))
      .filter((p) => p.ratio < p.min)
      .map((p) => `${p.fg} on ${p.bg} (${p.use}): ${p.ratio.toFixed(2)} < ${p.min}`);
    assert.deepEqual(failures, []);
  });
}
