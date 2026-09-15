"""The 10 trajectory-eval cases (deliverable 1) against the real cookbook
agent (app/agent/agent.py) and its 3 real tools (app/agent/tools.py) -
search_knowledge_base, substitute_ingredient, get_allergen_profile - over the
real ingested corpus (North_Indian_Home_Cooking.docx /
South_Indian_Home_Cooking.docx).

Each case names `required_tools` rather than one rigid call sequence, per the
"flexible assertions" requirement: a query like "does Paneer Butter Masala
have allergens?" has three legitimate ingredients (paneer/butter/cream) the
agent could reasonably check, and a case shouldn't fail just because it
checked a different one of them than some presumed "the" sequence.

`expected_facts` is graded by tests/llm_judge.py for the *outcome* eval
(deliverable 3's Gap = Outcome Pass Rate - Trajectory Pass Rate); the
trajectory pass/fail rule itself lives in evals/metrics.py and only ever
looks at which tools ran, never at the answer text.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TrajectoryCase:
    id: str
    question: str
    # Tools that MUST appear at least once in the trajectory for it to pass.
    required_tools: frozenset[str]
    # The golden/minimum number of tool-call steps - used for Step Efficiency.
    optimal_tool_calls: int
    # What the final answer must convey, for the outcome (llm_judge) eval.
    # For expect_answered=False cases, describes the *absence* of a claim.
    expected_facts: str
    # Tools that must NOT appear - wrong-tool-family calls, not just missing ones.
    forbidden_tools: frozenset[str] = field(default_factory=frozenset)
    # Tools that may legitimately appear beyond required_tools without being
    # counted as a wrong tool choice (e.g. a plausible but wrong ingredient
    # guess before the right one). Defaults to required_tools | search.
    valid_tools: frozenset[str] | None = None
    # False only for the one query the corpus genuinely can't answer - the
    # correct trajectory outcome there is a refusal, not "goal_completed".
    expect_answered: bool = True
    notes: str = ""

    def tools_considered_valid(self) -> frozenset[str]:
        if self.valid_tools is not None:
            return self.valid_tools
        return self.required_tools | {"search_knowledge_base"}


CASES: list[TrajectoryCase] = [
    TrajectoryCase(
        id="sambar_lentil",
        question="What lentil is used in Sambar?",
        required_tools=frozenset({"search_knowledge_base"}),
        forbidden_tools=frozenset({"substitute_ingredient", "get_allergen_profile"}),
        optimal_tool_calls=1,
        expected_facts="Sambar's main lentil is toor dal (split pigeon peas).",
        notes="Pure fact lookup - single tool, no substitution/allergen tool needed at all.",
    ),
    TrajectoryCase(
        id="dal_makhani_soak_time",
        question="How long do the urad dal and rajma need to soak before cooking Dal Makhani?",
        required_tools=frozenset({"search_knowledge_base"}),
        forbidden_tools=frozenset({"substitute_ingredient", "get_allergen_profile"}),
        optimal_tool_calls=1,
        expected_facts="The urad dal and rajma for Dal Makhani are soaked overnight (about 8 hours).",
        notes="Pure fact lookup, second flavor - guards against overfitting the metric to one query.",
    ),
    TrajectoryCase(
        id="paneer_vegan_butter",
        question="I'm vegan and making Paneer Butter Masala - what should I use instead of the butter?",
        required_tools=frozenset({"search_knowledge_base", "substitute_ingredient"}),
        optimal_tool_calls=2,
        expected_facts="A vegan substitute for butter is margarine or coconut oil.",
        notes="Recipe-grounded substitution - the fixed table's answer for (butter, vegan).",
    ),
    TrajectoryCase(
        id="dal_makhani_dairy_free_cream",
        question="What's a dairy-free substitute for the cream in Dal Makhani?",
        required_tools=frozenset({"search_knowledge_base", "substitute_ingredient"}),
        optimal_tool_calls=2,
        expected_facts="A dairy-free substitute for cream is coconut cream or cashew cream.",
        notes="Second substitution flavor, different ingredient/diet pair.",
    ),
    TrajectoryCase(
        id="aloo_paratha_gluten_free_flour",
        question="How do I make Aloo Paratha gluten-free instead of using the whole wheat flour?",
        required_tools=frozenset({"search_knowledge_base", "substitute_ingredient"}),
        optimal_tool_calls=2,
        expected_facts="A gluten-free substitute for wheat flour is a 1:1 gluten-free flour blend.",
        notes="Diet value differs from the vegan/dairy-free cases above (gluten-free).",
    ),
    TrajectoryCase(
        id="paneer_allergens",
        question="Does Paneer Butter Masala contain any common allergens?",
        required_tools=frozenset({"search_knowledge_base", "get_allergen_profile"}),
        optimal_tool_calls=2,
        valid_tools=frozenset({"search_knowledge_base", "get_allergen_profile"}),
        expected_facts=(
            "Paneer Butter Masala contains dairy (from paneer, butter, and/or cream) - "
            "any one of those three named as the dairy source is correct."
        ),
        notes=(
            "Flexible assertion: paneer, butter, and cream are all legitimate ingredients to "
            "check - the case only requires get_allergen_profile to run at least once, not on a "
            "specific one of the three."
        ),
    ),
    TrajectoryCase(
        id="payasam_allergens",
        question="What allergens should I watch out for in Payasam?",
        required_tools=frozenset({"search_knowledge_base", "get_allergen_profile"}),
        optimal_tool_calls=2,
        expected_facts="Payasam contains dairy (milk) and/or nuts (cashews) - either one named is correct.",
        notes=(
            "Unlike paneer_allergens, no ingredient is named in the question itself - the agent "
            "must read the search result to learn Payasam uses milk and cashews before it can "
            "even pick a get_allergen_profile argument. The grounding guard (agent.py) can't help "
            "here since it only extracts ingredients from the question text, not tool results - "
            "documented as a known guard limitation, not a bug."
        ),
    ),
    TrajectoryCase(
        id="gulab_jamun_vegan",
        question="Can I make Gulab Jamun vegan? What should replace the milk?",
        required_tools=frozenset({"search_knowledge_base", "substitute_ingredient"}),
        optimal_tool_calls=2,
        expected_facts="A vegan substitute for milk is soy milk, almond milk, or oat milk.",
        notes=(
            "Gulab Jamun's other milk-solid ingredient, khoya, has no table entry - a real "
            "no-known-substitute case if the agent tries it, distinct from milk succeeding."
        ),
    ),
    TrajectoryCase(
        id="bypass_probe_vegan_butter",
        question="What's a good vegan substitute for butter?",
        required_tools=frozenset({"substitute_ingredient"}),
        optimal_tool_calls=1,
        valid_tools=frozenset({"search_knowledge_base", "substitute_ingredient"}),
        expected_facts="A vegan substitute for butter is margarine or coconut oil.",
        notes=(
            "THE case this suite is built to expose (see GAP_ANALYSIS.md): no recipe is named, "
            "so nothing stops the agent from answering from pretrained memory without ever "
            "calling substitute_ingredient. Hypothesized as a right-answer-wrong-path risk; "
            "empirically it was worse than that - the pre-mitigation run recommended 'ghee' "
            "(dairy, not vegan) here, contradicting the fixed table's real answer. Trajectory-"
            "correct only if the table was actually consulted. This is the query the mitigation "
            "(agent.py's grounding guard) targets."
        ),
    ),
    TrajectoryCase(
        id="not_in_corpus_butter_chicken",
        question="What's the recipe for Butter Chicken?",
        required_tools=frozenset({"search_knowledge_base"}),
        forbidden_tools=frozenset({"substitute_ingredient", "get_allergen_profile"}),
        optimal_tool_calls=1,
        expect_answered=False,
        expected_facts=(
            "Butter Chicken is not in the cookbook corpus (only Paneer Butter Masala, Chole, "
            "Aloo Paratha, Dal Makhani, Jeera Rice, Gulab Jamun, Sambar, Masala Dosa, Curd Rice, "
            "Rasam, Coconut Chutney, and Payasam are) - the answer must say so, not invent a recipe."
        ),
        notes="Negative case: the trajectory-correct outcome is a refusal, never 'goal_completed'.",
    ),
]

CASES_BY_ID = {case.id: case for case in CASES}

assert len(CASES) == 10, f"expected exactly 10 trajectory cases, got {len(CASES)}"
