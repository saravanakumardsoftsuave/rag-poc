import { useState, type FormEvent } from "react";
import { SendIcon } from "./icons";

interface AskCardProps {
  onAsk: (question: string) => void;
  disabled: boolean;
}

const EXAMPLE = "Ask anything about your cookbooks";

export default function AskCard({ onAsk, disabled }: AskCardProps) {
  const [question, setQuestion] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || disabled) return;
    onAsk(trimmed);
    setQuestion("");
  }

  return (
    <section className="table" aria-label="Ask a question">
      <p className="table__eyebrow">Cookbook AI</p>
      <h2 className="table__title">What’s on your mind today?</h2>
      <form className="ruled-field" onSubmit={handleSubmit}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={EXAMPLE}
          aria-label="Your question"
          className="ruled-field__input"
        />
        <button type="submit" className="btn btn--stamp" disabled={disabled || !question.trim()}>
          <span className="ask-button-label">{disabled ? "Thinking…" : "Send"}</span>
          <SendIcon className="btn__icon" />
        </button>
      </form>
    </section>
  );
}
