import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { cx } from "./cx";
import { Drawer } from "./Drawer";
import { BREAKPOINTS, useMediaQuery } from "./useMediaQuery";

type Mode = "inline" | "drawer";

type Workspace = {
  sidebarMode: Mode;
  sourcesMode: Mode;
  openSidebar: () => void;
  sourcesOpen: boolean;
  setSourcesOpen: (open: boolean) => void;
  sourcesId: string; // for aria-controls on the toggle
};

const WorkspaceContext = createContext<Workspace | null>(null);

/** Layout state for header buttons; null outside a WorkspaceShell (components still work alone). */
export function useWorkspace(): Workspace | null {
  return useContext(WorkspaceContext);
}

type Props = {
  sidebar: ReactNode;
  header: ReactNode;
  composer: ReactNode;
  sources: ReactNode; // usually a SourcePanel
  sourcesLabel?: string; // name of the sources region / drawer
  sourcesOpen: boolean; // controlled: a citation click opens it
  onSourcesOpenChange: (open: boolean) => void;
  children: ReactNode; // the conversation, usually inside a ReadingColumn
};

const SOURCES_ID = "workspace-sources";

/**
 * Sidebar | conversation | sources. Wide screens (>= 1280px) show all three; from 1024px the sidebar
 * becomes a drawer; below 1024px the sources panel is a drawer too, opened on demand. Each column
 * scrolls on its own and the composer sits below the conversation, never over it.
 */
export function WorkspaceShell({ sidebar, header, composer, sources, sourcesLabel = "Sources", sourcesOpen, onSourcesOpenChange, children }: Props) {
  const sidebarMode: Mode = useMediaQuery(`(min-width: ${BREAKPOINTS.sidebarInline}px)`) ? "inline" : "drawer";
  const sourcesMode: Mode = useMediaQuery(`(min-width: ${BREAKPOINTS.sourcesInline}px)`) ? "inline" : "drawer";
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (sidebarMode === "inline") setSidebarOpen(false);
  }, [sidebarMode]);

  const ctx: Workspace = {
    sidebarMode,
    sourcesMode,
    openSidebar: () => setSidebarOpen(true),
    sourcesOpen,
    setSourcesOpen: onSourcesOpenChange,
    sourcesId: SOURCES_ID,
  };

  return (
    <WorkspaceContext.Provider value={ctx}>
      <div className={cx("ui-shell", sidebarMode === "inline" && "has-sidebar", sourcesMode === "inline" && sourcesOpen && "has-sources")}>
        {sidebarMode === "inline" ? (
          <aside className="ui-shell__sidebar" aria-label="Workspace">
            {sidebar}
          </aside>
        ) : (
          <Drawer side="left" title="Workspace" open={sidebarOpen} onClose={() => setSidebarOpen(false)}>
            {/* An action in the sidebar (a button, e.g. New conversation) also closes the drawer. */}
            <div className="ui-shell__drawer-sidebar" onClick={(e) => (e.target as HTMLElement).closest("button") && setSidebarOpen(false)}>
              {sidebar}
            </div>
          </Drawer>
        )}

        <main className="ui-shell__main">
          <div className="ui-shell__header">{header}</div>
          <div className="ui-shell__scroll">{children}</div>
          <div className="ui-shell__composer">{composer}</div>
        </main>

        {sourcesMode === "inline" ? (
          sourcesOpen && (
            <aside id={SOURCES_ID} className="ui-shell__sources" aria-label={sourcesLabel}>
              {sources}
            </aside>
          )
        ) : (
          <Drawer side="right" title={sourcesLabel} open={sourcesOpen} onClose={() => onSourcesOpenChange(false)}>
            <div id={SOURCES_ID} className="ui-shell__drawer-sources">
              {sources}
            </div>
          </Drawer>
        )}
      </div>
    </WorkspaceContext.Provider>
  );
}
