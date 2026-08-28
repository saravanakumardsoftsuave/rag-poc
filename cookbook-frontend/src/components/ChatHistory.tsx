import type { Conversation } from "../types";
import { relativeTime } from "../utils";
import { PlusIcon, TrashIcon } from "./icons";

interface ChatHistoryProps {
  conversations: Conversation[];
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

/** Groups chats the way people remember them: today, this week, older. */
function bucketOf(iso: string): string {
  const days = (Date.now() - new Date(iso).getTime()) / 86400000;
  if (days < 1) return "Today";
  if (days < 7) return "Previous 7 days";
  if (days < 30) return "Previous 30 days";
  return "Older";
}

export default function ChatHistory({ conversations, activeId, onSelect, onNew, onDelete }: ChatHistoryProps) {
  const sorted = [...conversations].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  const withHistory = sorted.filter((c) => c.turns.length > 0 || c.id === activeId);

  const groups: { label: string; items: Conversation[] }[] = [];
  for (const conversation of withHistory) {
    const label = bucketOf(conversation.updatedAt);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(conversation);
    else groups.push({ label, items: [conversation] });
  }

  return (
    <nav className="chats" aria-label="Chat history">
      <button type="button" className="chats__new" onClick={onNew}>
        <PlusIcon className="chats__new-icon" />
        New chat
      </button>

      {withHistory.length === 0 ? (
        <p className="chats__empty">Your past chats will collect here.</p>
      ) : (
        <div className="chats__scroll">
          {groups.map((group) => (
            <div className="chats__group" key={`${group.label}-${group.items[0].id}`}>
              <p className="chats__group-label">{group.label}</p>
              <ul className="chats__list">
                {group.items.map((conversation) => (
                  <li
                    key={conversation.id}
                    className={`chat-row ${conversation.id === activeId ? "chat-row--active" : ""}`}
                  >
                    <button
                      type="button"
                      className="chat-row__open"
                      onClick={() => onSelect(conversation.id)}
                      aria-current={conversation.id === activeId ? "true" : undefined}
                      title={conversation.title}
                    >
                      <span className="chat-row__title">{conversation.title}</span>
                      <span className="chat-row__meta">
                        {conversation.turns.length > 0
                          ? `${conversation.turns.length} message${conversation.turns.length === 1 ? "" : "s"} · ${relativeTime(conversation.updatedAt)}`
                          : "Empty"}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="chat-row__delete"
                      title={`Delete ${conversation.title}`}
                      aria-label={`Delete chat: ${conversation.title}`}
                      onClick={() => onDelete(conversation.id)}
                    >
                      <TrashIcon className="chat-row__delete-icon" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </nav>
  );
}
