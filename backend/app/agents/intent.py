from __future__ import annotations
from typing import Literal
from ..llm_router import chat_completions

Intent = Literal[
    "identity",         # asking your name / who you are
    "smalltalk",        # hi/hello/how are you/what's up
    "help_request",     # explicit ask for advice (help / what should I do / how to)
    "problem_question", # question about their situation (not identity)
    "venting",          # sharing feelings with no question
    "crisis_risk",      # self/other-harm cues (safety gate still handles final escalation)
    "other"
]

_SYSTEM = (
    "Classify a single user message into ONE intent label.\n"
    "Return ONLY one of: identity, smalltalk, help_request, problem_question, venting, crisis_risk, other.\n"
    "Guidelines:\n"
    "- identity: asking your name / who you are.\n"
    "- smalltalk: greetings or light chit-chat (hi/hello/how are you/what's up/etc.).\n"
    "- help_request: explicit ask for advice (help, what should I do, tips, how to...).\n"
    "- problem_question: question about their situation (how to handle exams, why do I feel X?), not identity.\n"
    "- venting: sharing feelings without a question or help request.\n"
    "- crisis_risk: self-harm or harm-to-others cues.\n"
)

async def classify_intent(user_text: str) -> Intent:
    user = f"Message: {user_text}\nLabel:"
    data = await chat_completions(
        "ROUTER",
        [{"role": "system", "content": _SYSTEM},
         {"role": "user", "content": user}],
        temperature=0.0, top_p=1.0
    )
    label = (data["choices"][0]["message"]["content"] or "").strip().lower()
    allowed = {"identity","smalltalk","help_request","problem_question","venting","crisis_risk","other"}
    return label if label in allowed else "other"
