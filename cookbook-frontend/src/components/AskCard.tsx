import { useState, type FormEvent } from "react";
import { SendIcon } from "./icons";

interface AskCardProps {
  onAsk: (question: string) => void;
  disabled: boolean;
}

const EXAMPLE = "How long should the lasagna rest before cutting?";

export default function AskCard({ onAsk, disabled }: AskCardProps) {
  const [question, setQuestion] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || disabled) return;
    onAsk(trimmed);
  }

  return (
    <section className="table" aria-label="Ask a question">
      <p className="table__eyebrow">Ask</p>
      <h2 className="table__title">What do you want to know?</h2>
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
          {disabled ? "Asking…" : "Ask"}
          <SendIcon className="btn__icon" />
        </button>
      </form>
    </section>
  );
}
