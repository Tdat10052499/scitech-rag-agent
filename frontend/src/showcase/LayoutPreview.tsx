import { useLayoutEffect, useRef, useState } from "react";
import type { ThemePreference } from "../ui";
import { Section } from "./Example";

const VIEWPORTS = [
  { id: "phone", label: "Phone 390", width: 390, height: 780 },
  { id: "tablet", label: "Tablet 834", width: 834, height: 900 },
  { id: "laptop", label: "Laptop 1280", width: 1280, height: 800 },
  { id: "wide", label: "Wide 1440", width: 1440, height: 860 },
] as const;

/**
 * The workspace specimen in a frame of a real width, so media queries, drawers and focus behave as on
 * that device. Frames wider than the page are scaled down for viewing only.
 */
export function LayoutPreview({ theme }: { theme: ThemePreference }) {
  const [vp, setVp] = useState<(typeof VIEWPORTS)[number]>(VIEWPORTS[2]);
  const [start, setStart] = useState<"conversation" | "empty">("conversation");
  const box = useRef<HTMLDivElement>(null);
  const [available, setAvailable] = useState(1000);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => entry && setAvailable(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const scale = Math.min(1, available / vp.width);
  const src = `showcase.html?view=specimen&theme=${theme}${start === "empty" ? "&start=empty" : ""}`;

  return (
    <Section
      id="layout"
      title="Layout specimen"
      intro={
        <p>
          The chat screen's own component (<code>src/chat/ChatWorkspace.tsx</code>, the same one <code>src/App.tsx</code> renders) fed with
          illustrative data and a simulated stream instead of the API, so no backend is needed. Below 1280px the sidebar becomes a drawer; below 1024px the sources panel does too. Type a question and press Enter; a question containing
          “insufficient” or “fail” shows those states.{" "}
          <a href={src} target="_blank" rel="noreferrer">
            Open the specimen full screen
          </a>
          .
        </p>
      }
    >
      <div className="sc-toolbar" role="group" aria-label="Preview settings">
        <fieldset className="ui-segmented">
          <legend className="ui-visually-hidden">Viewport width</legend>
          {VIEWPORTS.map((v) => (
            <label key={v.id} className={`ui-segmented__option${v.id === vp.id ? " is-checked" : ""}`}>
              <input type="radio" className="ui-visually-hidden" name="viewport" checked={v.id === vp.id} onChange={() => setVp(v)} />
              {v.label}
            </label>
          ))}
        </fieldset>
        <fieldset className="ui-segmented">
          <legend className="ui-visually-hidden">Starting state</legend>
          {(["conversation", "empty"] as const).map((s) => (
            <label key={s} className={`ui-segmented__option${s === start ? " is-checked" : ""}`}>
              <input type="radio" className="ui-visually-hidden" name="start" checked={s === start} onChange={() => setStart(s)} />
              {s === "conversation" ? "With conversation" : "Empty"}
            </label>
          ))}
        </fieldset>
        <span className="sc-toolbar__note">{scale < 1 ? `Scaled to ${Math.round(scale * 100)}% to fit` : "Actual size"}</span>
      </div>
      <div ref={box} className="sc-frame-box" style={{ height: vp.height * scale }}>
        <iframe
          key={src + vp.id}
          title={`Workspace specimen at ${vp.width}px`}
          src={src}
          className="sc-frame"
          style={{ width: vp.width, height: vp.height, transform: `scale(${scale})` }}
        />
      </div>
    </Section>
  );
}
