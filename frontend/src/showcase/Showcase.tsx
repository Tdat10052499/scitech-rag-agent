import { ThemeToggle, useThemePreference } from "../ui";
import { BookIcon } from "../ui/icons";
import { ILLUSTRATIVE_NOTE } from "./fixtures";
import { Foundations } from "./Foundations";
import { Gallery } from "./Gallery";
import { InteractionDemo } from "./InteractionDemo";
import { LayoutPreview } from "./LayoutPreview";

const NAV = [
  ["colors", "Color"],
  ["typography", "Typography"],
  ["shape", "Spacing · radius · motion"],
  ["basic", "Basic components"],
  ["research", "Research components"],
  ["interaction", "Citation interaction"],
  ["layout", "Layout specimen"],
] as const;

export default function Showcase() {
  const [theme, setTheme] = useThemePreference();
  return (
    <div className="sc">
      <a className="sc-skip" href="#main">
        Skip to content
      </a>
      <header className="sc-header">
        <div className="sc-header__brand">
          <span className="ui-sidebar__mark" aria-hidden="true">
            <BookIcon size={18} />
          </span>
          <div>
            <p className="sc-header__name">SciTech RAG · Design system</p>
            <p className="sc-header__status">
              <strong>Approved baseline · 2026-10-21.</strong> Used by the chat screen.
            </p>
          </div>
        </div>
        <ThemeToggle value={theme} onChange={setTheme} />
      </header>
      <div className="sc-body">
        <nav className="sc-nav" aria-label="Showcase sections">
          <ul>
            {NAV.map(([id, label]) => (
              <li key={id}>
                <a href={`#${id}`}>{label}</a>
              </li>
            ))}
          </ul>
        </nav>
        <main id="main" className="sc-main">
          <p className="sc-banner">{ILLUSTRATIVE_NOTE} Docs: frontend/docs/design-system/.</p>
          <Foundations />
          <Gallery theme={theme} onTheme={setTheme} />
          <InteractionDemo />
          <LayoutPreview theme={theme} />
        </main>
      </div>
    </div>
  );
}
