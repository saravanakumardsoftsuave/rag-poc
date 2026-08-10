RAG_SYSTEM_PROMPT = (
    "You are a helpful cooking assistant that answers questions using only the "
    "provided cookbook context. If the answer isn't in the context, say you don't "
    "know instead of guessing."
)


def build_prompt(question: str, context_chunks: list[str]) -> str:
    context = "\n\n".join(context_chunks)
    return f"{RAG_SYSTEM_PROMPT}\n\nContext:\n{context}\n\nQuestion: {question}\nAnswer:"
