import { ChatWorkspace } from "./chat/ChatWorkspace";
import { useChat } from "./chat/useChat";

// The chat screen: the approved design-system workspace (src/chat/ChatWorkspace.tsx) fed by the real
// conversation with POST /chat (src/chat/useChat.ts). No fixture data is used here.
export default function App() {
  return <ChatWorkspace chat={useChat()} />;
}
