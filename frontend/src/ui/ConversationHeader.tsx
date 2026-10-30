import type { ReactNode } from "react";
import { Button } from "./Button";
import { MenuIcon, PanelRightIcon, PlusIcon } from "./icons";
import { IconButton } from "./IconButton";
import { useWorkspace } from "./WorkspaceShell";

type Props = {
  title: string; // e.g. the first question, or "New conversation"
  sourcesCount?: number; // of the answer shown in the panel
  onNewConversation?: () => void; // shown here when the sidebar is not visible
  newConversationDisabled?: boolean;
  actions?: ReactNode;
};

/** 56px bar above the conversation. Inside a WorkspaceShell it adds the menu and sources toggles. */
export function ConversationHeader({ title, sourcesCount, onNewConversation, newConversationDisabled, actions }: Props) {
  const ws = useWorkspace();
  const sidebarHidden = ws?.sidebarMode === "drawer";
  return (
    <header className="ui-conversation-header">
      {sidebarHidden && <IconButton label="Open workspace menu" icon={<MenuIcon />} onClick={ws.openSidebar} tooltip={{ align: "start" }} />}
      <h1 className="ui-conversation-header__title" title={title}>
        {title}
      </h1>
      <div className="ui-conversation-header__actions">
        {actions}
        {(sidebarHidden || !ws) && onNewConversation && (
          <IconButton label="New conversation" icon={<PlusIcon />} onClick={onNewConversation} disabled={newConversationDisabled} />
        )}
        {ws && (
          <Button
            variant="ghost"
            size="sm"
            icon={<PanelRightIcon size={16} />}
            aria-expanded={ws.sourcesOpen}
            aria-controls={ws.sourcesOpen ? ws.sourcesId : undefined}
            className={ws.sourcesOpen ? "is-selected" : undefined}
            onClick={() => ws.setSourcesOpen(!ws.sourcesOpen)}
          >
            Sources{sourcesCount ? <span className="ui-count">{sourcesCount}</span> : null}
          </Button>
        )}
      </div>
    </header>
  );
}
