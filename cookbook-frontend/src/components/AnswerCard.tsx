import type { ReactNode } from "react";
import type { AskStatus, QueryResult } from "../types";
import { basename } from "../utils";
import { AlertIcon, PaperclipIcon } from "./icons";

interface AnswerCardProps {
  status: AskStatus;
  question: string;
  result: QueryResult | null;
  errorMessage: string | null;
  onRetry: () => void;
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
    const heading = line.match(/^\s*(#{1,3})\s+(.+)$/);
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

export default function AnswerCard({ status, question, result, errorMessage, onRetry }: AnswerCardProps) {
  if (status === "idle") {
    return (
      <section className="answer answer--idle" aria-live="polite">
        <p className="answer__idle-text">
          Your answer will show up here, with the exact cookbook pages it came from.
        </p>
      </section>
    );
  }

  if (status === "loading") {
    return (
      <section className="answer answer--loading" aria-busy="true" aria-live="polite">
        <p className="answer__question">&ldquo;{question}&rdquo;</p>
        <p className="answer__eyebrow">Reading your cookbooks…</p>
        <div className="answer__skeleton">
          <span />
          <span />
          <span style={{ width: "70%" }} />
        </div>
      </section>
    );
  }

  if (status === "error") {
    return (
      <section className="answer answer--error" aria-live="assertive">
        <p className="answer__eyebrow">
          <AlertIcon className="answer__alert-icon" /> Something went wrong
        </p>
        <p className="answer__error-text">{errorMessage}</p>
        <button type="button" className="btn btn--ghost" onClick={onRetry}>
          Try again
        </button>
      </section>
    );
  }

  if (!result) return null;

  const sourceNames = Array.from(new Set(result.sources.map(basename))).filter((s) => s && s !== "unknown");
  const shown = sourceNames.slice(0, 3);
  const overflow = sourceNames.length - shown.length;

  return (
    <section className="answer answer--done" aria-live="polite">
      <p className="answer__eyebrow">You asked</p>
      <p className="answer__question">&ldquo;{question}&rdquo;</p>
      <AnswerText text={result.answer} />

      {shown.length > 0 && (
        <div className="stamp-rack" aria-label="Pulled from">
          {shown.map((name, i) => (
            <span className={`stamp stamp--${i}`} key={name}>
              <PaperclipIcon className="stamp__clip" aria-hidden="true" />
              <span className="stamp__label">Pulled from</span>
              <span className="stamp__doc">{name}</span>
            </span>
          ))}
          {overflow > 0 && <span className="stamp__overflow">+{overflow} more page{overflow === 1 ? "" : "s"}</span>}
        </div>
      )}
    </section>
  );
}
