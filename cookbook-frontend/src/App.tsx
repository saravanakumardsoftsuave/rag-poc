import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Header from "./components/Header";
import DocumentBox from "./components/DocumentBox";
import ChatHistory from "./components/ChatHistory";
import AskCard from "./components/AskCard";
import AnswerCard from "./components/AnswerCard";
import { ApiError, askQuestion, checkHealth, deleteCookbook, getCookbooks, uploadCookbook } from "./api";
import type { ChatTurn, Conversation, CookbookDoc, UploadStatus } from "./types";
import { createConversation, loadActiveId, loadConversations, saveActiveId, saveConversations, titleFrom, uid } from "./storage";

export default function App() {
  const [documents, setDocuments] = useState<CookbookDoc[]>([]);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [conversations, setConversations] = useState<Conversation[]>(() => {
    const stored = loadConversations();
    return stored.length ? stored : [createConversation()];
  });
  const [activeId, setActiveId] = useState<string>(() => {
    const stored = loadConversations();
    const saved = loadActiveId();
    if (saved && stored.some((c) => c.id === saved)) return saved;
    return stored[0]?.id ?? "";
  });

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [kitchenStatus, setKitchenStatus] = useState<"checking" | "online" | "offline">("checking");
  const threadEndRef = useRef<HTMLDivElement>(null);

  // Keep an id pointing at a real conversation even after deletes.
  const active = useMemo(
    () => conversations.find((c) => c.id === activeId) ?? conversations[0],
    [conversations, activeId],
  );
  const turns = active?.turns ?? [];
  const isAsking = turns.some((turn) => turn.status === "loading");

  useEffect(() => {
    checkHealth().then((ok) => setKitchenStatus(ok ? "online" : "offline"));
    getCookbooks()
      .then(setDocuments)
      .catch((err) => setUploadError(err instanceof ApiError ? err.message : "Couldn't load your cookbooks."));
  }, []);

  useEffect(() => saveConversations(conversations), [conversations]);
  useEffect(() => {
    if (active) saveActiveId(active.id);
  }, [active]);

  useEffect(() => {
    if (turns.length) threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, isAsking]);

  const patchConversation = useCallback((id: string, update: (conversation: Conversation) => Conversation) => {
    setConversations((prev) => prev.map((c) => (c.id === id ? update(c) : c)));
  }, []);

  const patchTurn = useCallback(
    (conversationId: string, turnId: string, update: (turn: ChatTurn) => ChatTurn) => {
      patchConversation(conversationId, (conversation) => ({
        ...conversation,
        updatedAt: new Date().toISOString(),
        turns: conversation.turns.map((turn) => (turn.id === turnId ? update(turn) : turn)),
      }));
    },
    [patchConversation],
  );

  async function resolveTurn(conversationId: string, turnId: string, question: string) {
    try {
      const res = await askQuestion(question);
      patchTurn(conversationId, turnId, (turn) => ({
        ...turn,
        status: "done",
        answer: res.answer,
        sources: res.sources ?? [],
        error: null,
      }));
    } catch (err) {
      patchTurn(conversationId, turnId, (turn) => ({
        ...turn,
        status: "error",
        error: err instanceof ApiError ? err.message : "Something went wrong asking that question.",
      }));
    }
  }

  async function runAsk(question: string) {
    if (!active) return;
    const conversationId = active.id;
    const turn: ChatTurn = {
      id: uid(),
      status: "loading",
      question,
      answer: "",
      sources: [],
      error: null,
      askedAt: new Date().toISOString(),
    };

    patchConversation(conversationId, (conversation) => ({
      ...conversation,
      title: conversation.turns.length === 0 ? titleFrom(question) : conversation.title,
      turns: [...conversation.turns, turn],
      updatedAt: turn.askedAt,
    }));

    await resolveTurn(conversationId, turn.id, question);
  }

  async function retryTurn(turnId: string) {
    if (!active) return;
    const target = active.turns.find((t) => t.id === turnId);
    if (!target) return;
    patchTurn(active.id, turnId, (turn) => ({ ...turn, status: "loading", error: null }));
    await resolveTurn(active.id, turnId, target.question);
  }

  function handleNewChat() {
    // Reuse the current chat if it is still untouched instead of stacking empty ones.
    const empty = conversations.find((c) => c.turns.length === 0);
    if (empty) {
      setActiveId(empty.id);
    } else {
      const conversation = createConversation();
      setConversations((prev) => [conversation, ...prev]);
      setActiveId(conversation.id);
    }
    setSidebarOpen(false);
  }

  function handleSelectChat(id: string) {
    setActiveId(id);
    setSidebarOpen(false);
  }

  function handleDeleteChat(id: string) {
    const remaining = conversations.filter((c) => c.id !== id);
    const next = remaining.length ? remaining : [createConversation()];
    setConversations(next);
    if (id === active?.id) setActiveId(next[0].id);
  }

  async function handleUpload(file: File) {
    setUploadStatus("uploading");
    setUploadProgress(0);
    setUploadError(null);
    try {
      await uploadCookbook(file, setUploadProgress);
      await getCookbooks().then(setDocuments);
      setUploadStatus("idle");
    } catch (err) {
      setUploadStatus("error");
      setUploadError(err instanceof ApiError ? err.message : "That cookbook wouldn't file. Try again.");
    }
  }

  async function handleDelete(id: string) {
    setUploadError(null);
    try {
      await deleteCookbook(id);
      setDocuments((prev) => prev.filter((doc) => doc.id !== id));
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Couldn't delete that cookbook. Try again.");
    }
  }

  return (
    <div className="app app--chat">
      <Header
        kitchenStatus={kitchenStatus}
        onNewChat={handleNewChat}
        newChatDisabled={turns.length === 0}
        onToggleSidebar={() => setSidebarOpen((open) => !open)}
      />
      <main className={`layout ${turns.length > 0 ? "layout--conversation" : ""}`}>
        <div
          className={`sidebar__scrim ${sidebarOpen ? "sidebar__scrim--on" : ""}`}
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
        <aside className={`sidebar ${sidebarOpen ? "sidebar--open" : ""}`}>
          <ChatHistory
            conversations={conversations}
            activeId={active?.id ?? ""}
            onSelect={handleSelectChat}
            onNew={handleNewChat}
            onDelete={handleDeleteChat}
          />
          <DocumentBox
            documents={documents}
            status={uploadStatus}
            progress={uploadProgress}
            error={uploadError}
            onUpload={handleUpload}
            onDelete={handleDelete}
          />
        </aside>
        <div className="layout__main">
          {turns.map((turn) => (
            <AnswerCard key={turn.id} turn={turn} onRetry={retryTurn} />
          ))}
          {turns.length > 0 && <div ref={threadEndRef} className="thread__end" aria-hidden="true" />}
          <AskCard onAsk={runAsk} disabled={isAsking} />
          <p className="footnote">Cookbook AI can only answer from the cookbooks you upload.</p>
        </div>
      </main>
    </div>
  );
}
