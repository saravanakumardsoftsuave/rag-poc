import type { Conversation, ChatTurn } from "./types";

const CONVERSATIONS_KEY = "cookbook-ai.conversations.v1";
const ACTIVE_KEY = "cookbook-ai.active-conversation.v1";
const MAX_CONVERSATIONS = 50;

export function uid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function createConversation(): Conversation {
  const now = new Date().toISOString();
  return { id: uid(), title: "New chat", turns: [], createdAt: now, updatedAt: now };
}

/** First line of the opening question, trimmed to fit a sidebar row. */
export function titleFrom(question: string): string {
  const line = question.trim().split(/\r?\n/)[0] || "New chat";
  return line.length > 44 ? `${line.slice(0, 44).trimEnd()}…` : line;
}

function reviveTurn(raw: Partial<ChatTurn>): ChatTurn | null {
  if (!raw || typeof raw.question !== "string") return null;
  // A turn saved mid-flight can never resume after a reload — surface it as failed.
  const status = raw.status === "done" ? "done" : "error";
  return {
    id: typeof raw.id === "string" ? raw.id : uid(),
    status,
    question: raw.question,
    answer: typeof raw.answer === "string" ? raw.answer : "",
    sources: Array.isArray(raw.sources) ? raw.sources.filter((s): s is string => typeof s === "string") : [],
    error: status === "error" ? raw.error ?? "This answer didn't finish. Ask it again." : null,
    askedAt: typeof raw.askedAt === "string" ? raw.askedAt : new Date().toISOString(),
  };
}

export function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(CONVERSATIONS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Partial<Conversation>[];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((c): c is Partial<Conversation> => Boolean(c) && typeof c.id === "string")
      .map((c) => ({
        id: c.id as string,
        title: typeof c.title === "string" ? c.title : "New chat",
        turns: (Array.isArray(c.turns) ? c.turns : []).map(reviveTurn).filter((t): t is ChatTurn => t !== null),
        createdAt: typeof c.createdAt === "string" ? c.createdAt : new Date().toISOString(),
        updatedAt: typeof c.updatedAt === "string" ? c.updatedAt : new Date().toISOString(),
      }));
  } catch {
    return [];
  }
}

export function saveConversations(conversations: Conversation[]): void {
  try {
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations.slice(0, MAX_CONVERSATIONS)));
  } catch {
    // Storage full or blocked (private mode) — history is a convenience, not a requirement.
  }
}

export function loadActiveId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_KEY);
  } catch {
    return null;
  }
}

export function saveActiveId(id: string): void {
  try {
    localStorage.setItem(ACTIVE_KEY, id);
  } catch {
    // Ignore — see saveConversations.
  }
}
