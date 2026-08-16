RAG_SYSTEM_PROMPT = (
    "Answer the user's question only from the provided cookbook context. "
    "Give a complete, faithful answer: do not summarize, omit items, or stop partway through a list. "
    "Preserve the cookbook's useful structure with Markdown headings and lists where applicable. "
    "For an ingredients question, include every ingredient and its amount exactly as present in the context. "
    "Never invent missing recipe details. "
    "If the answer is not found, say: "
    "'I couldn't find an answer to that in the uploaded cookbooks.'"
)

def build_prompt(question: str, context_chunks: list[str]) -> str:
    context = "\n\n".join(context_chunks)
    return f"{RAG_SYSTEM_PROMPT}\n\nContext:\n{context}\n\nQuestion: {question}\nAnswer:"
