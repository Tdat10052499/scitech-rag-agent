import { ChatWorkspace } from "../chat/ChatWorkspace";
import type { ThemePreference } from "../ui";
import { CONVERSATION } from "./fixtures";
import { useSimulatedChat } from "./useSimulatedChat";

// Layout specimen: the SAME ChatWorkspace component as the app (src/App.tsx), fed by fixtures and a
// simulated stream instead of /chat. Typing "insufficient" or "fail" shows those states.

const params = new URLSearchParams(location.search);
const themeParam = params.get("theme");
const initialTheme: ThemePreference | undefined = themeParam === "light" || themeParam === "dark" || themeParam === "system" ? themeParam : undefined;

export default function Specimen() {
  const chat = useSimulatedChat(params.get("start") === "empty" ? [] : CONVERSATION);
  return <ChatWorkspace chat={chat} initialTheme={initialTheme} />;
}
