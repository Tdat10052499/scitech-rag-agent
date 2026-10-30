import type { ReactNode } from "react";

/** A titled specimen in the showcase. `note` says what to look for or what is a proposal. */
export function Example({ title, note, children, wide = false }: { title: string; note?: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <figure className={wide ? "sc-example sc-example--wide" : "sc-example"}>
      <figcaption className="sc-example__caption">
        <span className="sc-example__title">{title}</span>
        {note && <span className="sc-example__note">{note}</span>}
      </figcaption>
      <div className="sc-example__stage">{children}</div>
    </figure>
  );
}

export function Section({ id, title, intro, children }: { id: string; title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="sc-section" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="sc-section__title">
        {title}
      </h2>
      {intro && <div className="sc-section__intro">{intro}</div>}
      {children}
    </section>
  );
}

export function Grid({ children, min = 280 }: { children: ReactNode; min?: number }) {
  return (
    <div className="sc-grid" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(min(100%, ${min}px), 1fr))` }}>
      {children}
    </div>
  );
}
