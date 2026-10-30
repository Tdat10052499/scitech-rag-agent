import { useId } from "react";
import type { ReactNode } from "react";
import { Button } from "./Button";
import { BookIcon, PlusIcon } from "./icons";

type Props = {
  productName?: string;
  onNewConversation: () => void;
  newConversationDisabled?: boolean;
  children?: ReactNode; // SidebarSection blocks; only real content (the app has no history yet)
  footer?: ReactNode; // e.g. ThemeToggle
};

/** Left column: product name, the one global action, short facts about the corpus, settings. */
export function Sidebar({ productName = "SciTech RAG", onNewConversation, newConversationDisabled, children, footer }: Props) {
  return (
    <div className="ui-sidebar">
      <div className="ui-sidebar__brand">
        <span className="ui-sidebar__mark" aria-hidden="true">
          <BookIcon size={18} />
        </span>
        <span className="ui-sidebar__name">{productName}</span>
      </div>
      <Button variant="secondary" icon={<PlusIcon size={16} />} onClick={onNewConversation} disabled={newConversationDisabled} className="ui-sidebar__new">
        New conversation
      </Button>
      <div className="ui-sidebar__sections">{children}</div>
      {footer && <div className="ui-sidebar__footer">{footer}</div>}
    </div>
  );
}

export function SidebarSection({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section className="ui-sidebar__section" aria-labelledby={id}>
      <h2 id={id} className="ui-label">
        {title}
      </h2>
      <div className="ui-sidebar__section-body">{children}</div>
    </section>
  );
}
