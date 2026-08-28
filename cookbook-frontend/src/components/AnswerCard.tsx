import type { ReactNode } from "react";
import type { ChatTurn } from "../types";
import { AlertIcon } from "./icons";

interface AnswerCardProps {
  turn: ChatTurn;
  onRetry: (turnId: string) => void;
}

function formatInline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> : part,
  );
}

function AnswerText({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let listItems: string[] = [];
  let listType: "ul" | "ol" = "ul";

  const flushList = () => {
    if (!listItems.length) return;
    const items = listItems.map((item, index) => <li key={index}>{formatInline(item)}</li>);
    blocks.push(listType === "ol" ? <ol className="answer__list" key={blocks.length}>{items}</ol> : <ul className="answer__list" key={blocks.length}>{items}</ul>);
    listItems = [];
  };

  for (const line of text.split(/\r?\n/)) {
    const heading = line.match(/^\s*(#{1,6})\s+(.+)$/);
    const match = line.match(/^\s*(?:(\d+)\.|[-*])\s+(.+)$/);
    if (heading) {
      flushList();
      const level = heading[1].length;
      const content = formatInline(heading[2]);
      blocks.push(
        level === 1 ? <h2 className="answer__heading answer__heading--1" key={blocks.length}>{content}</h2> :
        <h3 className="answer__heading" key={blocks.length}>{content}</h3>,
      );
    } else if (match) {
      const nextListType = match[1] ? "ol" : "ul";
      if (listItems.length && listType !== nextListType) flushList();
      listType = nextListType;
      listItems.push(match[2]);
    } else if (line.trim()) {
      flushList();
      blocks.push(<p className="answer__paragraph" key={blocks.length}>{formatInline(line.trim())}</p>);
    }
  }
  flushList();

  return <div className="answer__text">{blocks}</div>;
}

/** One question-and-answer exchange in the thread. */
export default function AnswerCard({ turn, onRetry }: AnswerCardProps) {
  if (turn.status === "loading") {
    return (
      <section className="answer answer--loading" aria-busy="true" aria-live="polite">
        <p className="answer__question">&ldquo;{turn.question}&rdquo;</p>
        <p className="answer__eyebrow">Reading your cookbooks…</p>
        <div className="answer__skeleton">
          <span />
          <span />
          <span style={{ width: "70%" }} />
        </div>
      </section>
    );
  }

  if (turn.status === "error") {
    return (
      <section className="answer answer--error" aria-live="assertive">
        <p className="answer__question">&ldquo;{turn.question}&rdquo;</p>
        <p className="answer__eyebrow">
          <AlertIcon className="answer__alert-icon" /> Something went wrong
        </p>
        <p className="answer__error-text">{turn.error}</p>
        <button type="button" className="btn btn--ghost" onClick={() => onRetry(turn.id)}>
          Try again
        </button>
      </section>
    );
  }

  return (
    <section className="answer answer--done" aria-live="polite">
      <p className="answer__eyebrow">You asked</p>
      <p className="answer__question">&ldquo;{turn.question}&rdquo;</p>
      <AnswerText text={turn.answer} />
    </section>
  );
}
