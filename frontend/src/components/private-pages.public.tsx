// Public-build stand-ins: chat and memory only run on the owner's own Mac (127.0.0.1:7317).
import LocalOnly from "@/components/LocalOnly";

export function ChatPage() { return <LocalOnly page="chat" />; }
export function MemoryPage() { return <LocalOnly page="memory" />; }
export const PUBLIC_BUILD = true;
