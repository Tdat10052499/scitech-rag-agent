import { useEffect, useLayoutEffect, useRef, useState } from "react";
import "@fontsource/cormorant-garamond/500.css"; // showcase only: comparison specimen for the review
import { CONTRAST_PAIRS, contrastRatio, parseColor, toHex } from "../ui/contrast";
import { FONT_FAMILIES } from "../ui/fonts";
import { useMediaQuery } from "../ui/useMediaQuery";
import { Example, Grid, Section } from "./Example";

const COLOR_GROUPS: Array<{ name: string; tokens: Array<[string, string]> }> = [
  {
    name: "Background",
    tokens: [
      ["--color-bg-canvas", "Page"],
      ["--color-bg-surface", "Sidebar, user turn, code"],
      ["--color-bg-elevated", "Composer, drawer, secondary button"],
      ["--color-bg-hover", "Hovered row or button"],
      ["--color-bg-selected", "Selected source, pressed toggle"],
      ["--color-bg-highlight", "Start of the cited-source flash"],
      ["--color-bg-disabled", "Disabled control"],
    ],
  },
  {
    name: "Text",
    tokens: [
      ["--color-text", "Answer, titles, UI"],
      ["--color-text-secondary", "Metadata, hints, labels"],
      ["--color-text-disabled", "Disabled (exempt from contrast)"],
      ["--color-text-link", "Links, citation numbers"],
      ["--color-text-on-accent", "Text on accent fill"],
    ],
  },
  {
    name: "Border, accent, focus",
    tokens: [
      ["--color-border", "Dividers (decorative)"],
      ["--color-border-strong", "Control boundaries, >= 3:1"],
      ["--color-accent", "Primary button, active citation"],
      ["--color-accent-hover", "Primary hover"],
      ["--color-accent-soft", "Citation chip, selected"],
      ["--color-focus-ring", "Keyboard focus"],
    ],
  },
  {
    name: "Status",
    tokens: [
      ["--color-warning-bg", "Insufficient evidence"],
      ["--color-warning-border", ""],
      ["--color-warning-text", ""],
      ["--color-warning-icon", ""],
      ["--color-error-bg", "Technical error"],
      ["--color-error-border", ""],
      ["--color-error-text", ""],
      ["--color-info-bg", "Neutral information"],
      ["--color-info-text", ""],
    ],
  },
];

const SCHEMES = ["light", "dark"] as const;

/** Resolve tokens to colors through real CSS in a forced-theme probe. */
function useResolvedColors(tokens: string[]) {
  const probes = useRef<Record<string, HTMLSpanElement | null>>({});
  const [values, setValues] = useState<Record<string, string>>({});
  const key = tokens.join();
  useLayoutEffect(() => {
    const out: Record<string, string> = {};
    for (const scheme of SCHEMES) {
      const el = probes.current[scheme];
      if (!el) continue;
      for (const t of tokens) {
        el.style.color = `var(${t})`;
        out[`${scheme}${t}`] = getComputedStyle(el).color;
      }
    }
    setValues(out);
  }, [key]); // probes force their theme, so the page theme does not change these values
  const probeEls = SCHEMES.map((s) => <span key={s} data-theme={s} ref={(el) => void (probes.current[s] = el)} hidden />);
  return { values, probeEls };
}

const ALL_TOKENS = [...new Set([...COLOR_GROUPS.flatMap((g) => g.tokens.map(([t]) => t)), ...CONTRAST_PAIRS.flatMap((p) => [p.fg, p.bg])])];

function show(css: string | undefined): string {
  if (!css) return "…";
  const rgb = parseColor(css);
  return rgb && !/rgba|\/\s*0?\./.test(css) ? toHex(rgb) : css;
}

function Colors() {
  const { values, probeEls } = useResolvedColors(ALL_TOKENS);
  return (
    <>
      {probeEls}
      {COLOR_GROUPS.map((g) => (
        <Example key={g.name} title={g.name} wide>
          <table className="sc-table">
            <thead>
              <tr>
                <th scope="col">Token</th>
                <th scope="col">Light</th>
                <th scope="col">Dark</th>
                <th scope="col">Use</th>
              </tr>
            </thead>
            <tbody>
              {g.tokens.map(([t, use]) => (
                <tr key={t}>
                  <td>
                    <code>{t}</code>
                  </td>
                  {SCHEMES.map((s) => (
                    <td key={s}>
                      <span className="sc-swatch-cell">
                        <span className="sc-swatch" data-theme={s} style={{ background: `var(${t})` }} />
                        <code>{show(values[`${s}${t}`])}</code>
                      </span>
                    </td>
                  ))}
                  <td>{use}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Example>
      ))}
      <Example
        title="Contrast of the pairs the components render"
        note="Computed live from the CSS in each theme. The same list is checked by npm test (src/ui/contrast.test.ts). Minimum: 4.5 for text, 3 for icons, borders and focus."
        wide
      >
        <table className="sc-table">
          <thead>
            <tr>
              <th scope="col">Pair</th>
              <th scope="col">Used for</th>
              <th scope="col">Light</th>
              <th scope="col">Dark</th>
            </tr>
          </thead>
          <tbody>
            {CONTRAST_PAIRS.map((p) => (
              <tr key={`${p.fg}${p.bg}`}>
                <td>
                  <span className="sc-pair" data-theme="light" style={{ color: `var(${p.fg})`, background: `var(${p.bg})` }}>
                    Aa
                  </span>
                  <span className="sc-pair" data-theme="dark" style={{ color: `var(${p.fg})`, background: `var(${p.bg})` }}>
                    Aa
                  </span>
                  <code>
                    {p.fg} / {p.bg}
                  </code>
                </td>
                <td>{p.use}</td>
                {SCHEMES.map((s) => {
                  const fg = parseColor(values[`${s}${p.fg}`] ?? "");
                  const bg = parseColor(values[`${s}${p.bg}`] ?? "");
                  const r = fg && bg ? contrastRatio(fg, bg) : null;
                  return (
                    <td key={s} className={r !== null && r < p.min ? "sc-fail" : undefined}>
                      {r === null ? "…" : `${r.toFixed(2)} ${r >= p.min ? "pass" : "FAIL"}`}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </Example>
    </>
  );
}

const VI_SAMPLE = "Mô hình ngôn ngữ lớn trả lời dựa trên bằng chứng truy xuất — Ở đâu? Ượt, ữa, ỹ, ặ, ẫ, Đ.";

const TYPE_STEPS: Array<{ name: string; cls: string; spec: string; sample: string }> = [
  { name: "Display", cls: "sc-type-display", spec: "Newsreader 30px / 1.2, 400, -0.01em (26px on phones)", sample: "What would you like to know about language-model research?" },
  { name: "Title", cls: "sc-type-title", spec: "Inter 18px / 1.35, 600", sample: "Sources for answer 2" },
  { name: "Answer body", cls: "sc-type-answer", spec: "Inter 16px / 1.7, 400", sample: "Retrieval-augmented generation pairs a language model with a retriever that fetches passages for each question." },
  { name: "UI / body", cls: "sc-type-body", spec: "Inter 14px / 1.55, 400–600", sample: "Dense Passage Retrieval for Open-Domain Question Answering" },
  { name: "Metadata", cls: "sc-type-meta", spec: "Inter 13px / 1.45, secondary color", sample: "arXiv · 2020 · arXiv:2004.04906" },
  { name: "Label", cls: "ui-label", spec: "Inter 12px / 1.4, 600, uppercase, +0.04em", sample: "Follow-up questions" },
  { name: "Code", cls: "sc-type-code", spec: "JetBrains Mono 13px / 1.6", sample: "retriever.search(query, k=5)  # cs.CL" },
];

function FontStatus() {
  const [status, setStatus] = useState<Record<string, boolean | null>>({});
  useEffect(() => {
    let alive = true;
    // Load each family with Vietnamese text, then ask the browser whether that face is really available.
    const checks = Object.values(FONT_FAMILIES).map((f) => `16px "${f}"`);
    void Promise.all(checks.map((c) => document.fonts.load(c, VI_SAMPLE))).finally(() => {
      if (!alive) return;
      setStatus(Object.fromEntries(Object.values(FONT_FAMILIES).map((f) => [f, document.fonts.check(`16px "${f}"`, VI_SAMPLE)])));
    });
    return () => {
      alive = false;
    };
  }, []);
  return (
    <ul className="sc-font-status">
      {Object.entries(FONT_FAMILIES).map(([role, family]) => (
        <li key={role}>
          <strong>{role}</strong>: {family} —{" "}
          {status[family] === undefined ? "checking…" : status[family] ? "loaded (self-hosted, Vietnamese subset)" : "NOT loaded, fallback in use"}
        </li>
      ))}
    </ul>
  );
}

function Typography() {
  return (
    <>
      <Example title="Fonts actually in use" note="Checked in this browser with document.fonts. Copernicus/Tiempos and StyreneB are licensed and not available to the project, so open-source substitutes are used; they are not claimed to match.">
        <FontStatus />
      </Example>
      <Example title="Type scale" wide>
        <div className="sc-type-list">
          {TYPE_STEPS.map((t) => (
            <div key={t.name} className="sc-type-row">
              <div className="sc-type-meta-col">
                <strong>{t.name}</strong>
                <span>{t.spec}</span>
              </div>
              <div>
                <p className={t.cls}>{t.sample}</p>
                <p className={t.cls}>{VI_SAMPLE}</p>
              </div>
            </div>
          ))}
        </div>
      </Example>
      <Example
        title="Display serif: chosen vs. the substitute named in DESIGN-claude.md"
        note="For review. Newsreader (chosen): larger x-height and sturdier strokes at 26–30px, close to an editorial text face. Cormorant Garamond (suggested): elegant, but thin and small at this size, especially the Vietnamese stacked marks."
        wide
      >
        <div className="sc-compare">
          <div>
            <span className="ui-label">Newsreader 400</span>
            <p className="sc-type-display">Bạn muốn tìm hiểu điều gì về nghiên cứu mô hình ngôn ngữ?</p>
          </div>
          <div>
            <span className="ui-label">Cormorant Garamond 500</span>
            <p className="sc-type-display" style={{ fontFamily: '"Cormorant Garamond", serif', fontWeight: 500 }}>
              Bạn muốn tìm hiểu điều gì về nghiên cứu mô hình ngôn ngữ?
            </p>
          </div>
        </div>
      </Example>
    </>
  );
}

const SPACES = [1, 2, 3, 4, 6, 8, 12];
const RADII: Array<[string, string]> = [
  ["--radius-sm", "6px · badges, citations"],
  ["--radius-md", "8px · buttons, inputs"],
  ["--radius-lg", "12px · callouts, sources"],
  ["--radius-xl", "16px · composer"],
];

function Shapes() {
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)");
  const [flash, setFlash] = useState(0);
  return (
    <Grid min={300}>
      <Example title="Spacing (4px base)">
        <div className="sc-spaces">
          {SPACES.map((s) => (
            <div key={s} className="sc-space-row">
              <code>--space-{s}</code>
              <span className="sc-space-bar" style={{ width: `var(--space-${s})` }} />
              <span>{s * 4}px</span>
            </div>
          ))}
        </div>
      </Example>
      <Example title="Radius">
        <div className="sc-radii">
          {RADII.map(([t, label]) => (
            <div key={t} className="sc-radius" style={{ borderRadius: `var(${t})` }}>
              <code>{t}</code>
              <span>{label}</span>
            </div>
          ))}
        </div>
      </Example>
      <Example title="Elevation" note="Color and borders first; shadows only on floating layers.">
        <div className="sc-elevations">
          <div className="sc-elev" style={{ border: "1px solid var(--color-border)" }}>
            Border only
            <small>panels, lists</small>
          </div>
          <div className="sc-elev" style={{ boxShadow: "var(--shadow-sm)", border: "1px solid var(--color-border-strong)" }}>
            --shadow-sm
            <small>composer, checked segment</small>
          </div>
          <div className="sc-elev" style={{ boxShadow: "var(--shadow-md)" }}>
            --shadow-md
            <small>drawer</small>
          </div>
        </div>
      </Example>
      <Example title="Motion" note={reduced ? "Reduced motion is ON in this browser: durations are 0, the flash and pulsing dots are off." : "Reduced motion is off. Turn it on in the OS to see the static versions."}>
        <ul className="sc-motion">
          <li>
            <code>--duration-fast</code> 120ms · hover, press
          </li>
          <li>
            <code>--duration-base</code> 200ms · tooltip
          </li>
          <li>
            <code>--duration-slow</code> 280ms · drawer slide
          </li>
          <li>
            <code>--duration-highlight</code> 1600ms · cited-source flash
          </li>
        </ul>
        <div className="sc-flash-demo">
          <div className="ui-source is-active">
            {flash > 0 && <span key={flash} className="ui-source__flash" aria-hidden="true" />}
            <span className="ui-source__number">2</span>
            <div className="ui-source__body">
              <p className="ui-source__title">Highlight of a cited source</p>
            </div>
          </div>
          <button type="button" className="ui-text-button" onClick={() => setFlash(flash + 1)}>
            Play highlight
          </button>
        </div>
      </Example>
    </Grid>
  );
}

export function Foundations() {
  return (
    <>
      <Section id="colors" title="Color" intro={<p>Semantic tokens only; each is defined once with <code>light-dark()</code>. Values below are read from the live CSS.</p>}>
        <Colors />
      </Section>
      <Section id="typography" title="Typography">
        <Typography />
      </Section>
      <Section id="shape" title="Spacing, radius, elevation, motion">
        <Shapes />
      </Section>
    </>
  );
}
