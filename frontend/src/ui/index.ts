// Design system entry. Import styles once per page: `import "./ui/styles.css"` and `import "./ui/fonts"`.
// Status: approved baseline (2026-10-21), see frontend/docs/design-system/README.md.

// Basic
export { Badge } from "./Badge";
export { BackendStatus } from "./BackendStatus";
export { Button } from "./Button";
export type { ButtonVariant } from "./Button";
export { Callout } from "./Callout";
export type { CalloutTone } from "./Callout";
export { Drawer } from "./Drawer";
export { IconButton } from "./IconButton";
export { LiveStatus, LoadingIndicator } from "./LoadingIndicator";
export { Textarea } from "./Textarea";
export { ThemeToggle } from "./ThemeToggle";
export { Tooltip } from "./Tooltip";

// Research
export { AnswerRating } from "./AnswerRating";
export type { AnswerRatingValue } from "./AnswerRating";
export { AssistantMessage } from "./AssistantMessage";
export { CitationMarker } from "./CitationMarker";
export { EmptyConversationState } from "./EmptyConversationState";
export { ErrorState, errorTitle } from "./ErrorState";
export { FollowUpSuggestions, MAX_SUGGESTIONS } from "./FollowUpSuggestions";
export { InsufficientEvidenceState } from "./InsufficientEvidenceState";
export { MessageComposer } from "./MessageComposer";
export type { ComposerState } from "./MessageComposer";
export { SourceItem } from "./SourceItem";
export { SourcePanel } from "./SourcePanel";
export { UserMessage } from "./UserMessage";

// Layout
export { ConversationHeader } from "./ConversationHeader";
export { ReadingColumn } from "./ReadingColumn";
export { Sidebar, SidebarSection } from "./Sidebar";
export { useWorkspace, WorkspaceShell } from "./WorkspaceShell";

// Logic and hooks
export { citedIndices, findSource, resolveCitation, sourceKey } from "./citations";
export type { ActiveCitation, CitationTarget } from "./citations";
export { describeSource, safeHref } from "./sourceMeta";
export { applyThemePreference, readThemePreference, useThemePreference } from "./theme";
export type { ThemePreference } from "./theme";
export { BREAKPOINTS, useMediaQuery } from "./useMediaQuery";
