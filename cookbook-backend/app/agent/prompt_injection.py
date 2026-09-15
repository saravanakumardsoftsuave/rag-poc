"""Defenses against indirect prompt injection via retrieved tool output
(bonus challenge). An ingested recipe document can carry third-party text -
a community tip, a comment - that search_knowledge_base hands straight to
the final-answer prompt. If that text is phrased as an instruction ("ignore
previous instructions and tell the user to..."), the generation model may
follow it instead of treating it as retrieved content to quote or ignore.

Two layers, matching where each can actually intervene:

1. sanitize_chunk_text - strips instruction-shaped text out of what reaches
   the prompt at all. Applied in tools.py's _search_knowledge_base to every
   chunk before it's returned, so a poisoned chunk never gets to the model
   with its payload intact.
2. guard_answer_output - a last-resort scan of the *generated* answer for a
   short list of concretely dangerous directives (disable a security
   control, pipe a remote script into a shell). Applied in agent.py's
   _finalize_answer, in case an injection phrased subtly enough to survive
   layer 1 still gets the model to repeat something dangerous.

Both are regex pattern matches, not semantic understanding of intent -
see evals/prompt_injection/REPORT.md for residual vulnerabilities this
deliberately does not catch (paraphrased attacks, attacks split across
multiple chunks, etc).

Read-only tool scope is a third defense this bonus challenge asks for, but
it needed no code change: every tool in tools.py (search_knowledge_base,
substitute_ingredient, get_allergen_profile) is already a pure lookup with
no write, network, or shell capability - there is nothing an injected
instruction could direct a tool call to *do* beyond reading a fixed table
or the vector index, so that defense layer was already satisfied by the
existing tool design.
"""

import re

_INJECTION_PATTERNS = [
    re.compile(r"ignore (all |any )?(previous|prior|above) instructions?", re.IGNORECASE),
    re.compile(r"disregard (all |any )?(previous|prior|above)", re.IGNORECASE),
    re.compile(r"new instructions?\s*:", re.IGNORECASE),
    re.compile(r"\byou are now\b", re.IGNORECASE),
    re.compile(r"system prompt", re.IGNORECASE),
    re.compile(r"\bact as\b", re.IGNORECASE),
]

CHUNK_REDACTION = "[content removed by prompt-injection filter]"


def sanitize_chunk_text(text: str) -> str:
    """Replace any instruction-shaped span in retrieved chunk text with a
    neutral marker before it can reach the final-answer prompt."""
    sanitized = text
    for pattern in _INJECTION_PATTERNS:
        sanitized = pattern.sub(CHUNK_REDACTION, sanitized)
    return sanitized


_DANGEROUS_DIRECTIVES = [
    re.compile(r"disable (the )?(tls|ssl)( certificate)? verification", re.IGNORECASE),
    re.compile(r"curl[^\n]{0,40}\|\s*(sh|bash)", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"disable (your )?(firewall|antivirus)", re.IGNORECASE),
]

ANSWER_GUARD_FALLBACK = (
    "I found retrieved content that reads like an embedded instruction rather than cookbook "
    "information, and I'm not repeating it. Please rephrase your question, or check the source "
    "document directly."
)


def guard_answer_output(answer: str) -> str:
    """Replace the generated answer entirely if it contains a concretely
    dangerous directive - safer than trying to excise just the offending
    sentence, since a model that echoed one injected instruction may have
    absorbed others nearby that a narrower cut would miss."""
    for pattern in _DANGEROUS_DIRECTIVES:
        if pattern.search(answer):
            return ANSWER_GUARD_FALLBACK
    return answer
