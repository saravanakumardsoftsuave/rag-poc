import ast
import operator
import re

from app.prompt import build_general_prompt
from app.rag import answer_question, generate_answer

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}

_EXPRESSION_PATTERN = re.compile(r"[-+*/().\d\s%]*\d[-+*/().\d\s%]*")


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported expression node: {node!r}")


def calculator_tool(question: str) -> dict:
    """Performs an arithmetic calculation, e.g. scaling a recipe's quantities
    or converting a measurement. Give it the expression as plain text."""
    match = _EXPRESSION_PATTERN.search(question)
    expression = match.group().strip() if match else ""
    if not expression:
        return {"answer": "I couldn't find a calculation to perform in that question.", "sources": []}
    try:
        result = _safe_eval(ast.parse(expression, mode="eval").body)
    except (SyntaxError, ValueError, ZeroDivisionError):
        return {"answer": f"I couldn't evaluate '{expression}' as a calculation.", "sources": []}
    return {"answer": f"{expression} = {result}", "sources": []}


def rag_tool(question: str) -> dict:
    """Answers open-ended questions about recipes, ingredients, or cooking
    instructions found in the uploaded cookbooks using retrieval-augmented
    generation. Does not scale servings or suggest allergen substitutes."""
    return answer_question(question)


def general_tool(question: str) -> dict:
    """Handles greetings, thanks, or questions about the assistant itself -
    anything that needs neither a cookbook lookup nor a calculation."""
    answer = generate_answer(build_general_prompt(question))
    return {"answer": answer, "sources": []}
