"""LLM-as-judge grading for E2E tests.

An E2E test runs the real generation model, so its output isn't byte-exact -
wording varies even with do_sample=False across environments/model versions.
A substring assertion (`"toor dal" in answer`) is brittle: it fails on
paraphrases ("pigeon peas") and passes on garbage that happens to contain the
word. An LLM judge grades whether the answer conveys the expected facts
semantically, the same way a human reviewer would read it.

Uses the same local model that generates the RAG answer (app.rag.get_generator,
Qwen2.5-1.5B-Instruct per HF_GENERATION_MODEL) rather than an external API, so
the test needs no extra credentials or network call to grade.

Trade-off worth knowing: grading an answer with the same (small) model that
produced it means the judge can share the model's own blind spots - e.g. if
Qwen2.5 is weak at negation, it may also misjudge a negation question's
verdict. This is fine for a smoke-test-style e2e check, but isn't as reliable
a signal as grading with a larger/independent model.
"""

from app.config import settings
from app.rag import get_generator

JUDGE_PROMPT = """You are grading a cooking-assistant chatbot's answer for factual correctness.

Question asked: {question}

Facts the answer must correctly convey: {expected_facts}

Chatbot's answer: {answer}

Does the chatbot's answer convey those facts correctly, without contradicting
or reversing any of them? Minor differences in wording, tone, or extra correct
detail are fine - only fail it for missing or wrong facts.

Reply with exactly one line: PASS or FAIL, followed by a dash and a one-sentence reason."""


def judge_answer(question: str, answer: str, expected_facts: str) -> tuple[bool, str]:
    """Returns (passed, raw_verdict_text)."""
    prompt = JUDGE_PROMPT.format(question=question, expected_facts=expected_facts, answer=answer)
    output = get_generator()(
        [{"role": "user", "content": prompt}],
        max_new_tokens=settings.hf_generation_max_new_tokens,
        do_sample=False,
    )
    verdict = output[0]["generated_text"][-1]["content"].strip()
    first_line = verdict.splitlines()[0] if verdict else ""
    passed = first_line.strip().upper().startswith("PASS")
    return passed, verdict
