"""Finance-specific content check: the Validator only checks structure (right
sections, right counts, no truncation). It has no idea whether the numbers
in the brief are *true*. This is the gap the WAM doc calls "the bigger WAM
opportunity": financial source conflicts, stale data, unsupported claims.

This is an optional, separate pass (not part of detect_all) because it's an
LLM call over real financial content, not a free structural regex check —
run it deliberately, e.g. only on attempts that already passed structural
validation, so cost is spent judging brief content that's actually a
candidate for shipping.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from shadowdesk.reliability.ollama_client import DEFAULT_MODEL, OllamaError, chat_json

SYSTEM_PROMPT = """You are a financial fact-checker reviewing an AI-generated daily
market brief against the source data it was supposed to be based on. You are not
grading the writing. Find only concrete, checkable problems:

- financial_contradiction: a number, direction, or claim in the brief conflicts with
  the source data (e.g. brief says a stock is up, source data shows it down).
- stale_information: the brief presents old data as current, or ignores a source
  entry that is clearly more recent for the same fact.
- unsupported_claim: the brief asserts something (a figure, an event, a causal claim)
  that has no corresponding entry anywhere in the source data.

Respond with ONLY JSON: {"findings": [{"type": "<one of the three above>",
"claim": "<quote or paraphrase from the brief>", "explanation": "<why it's a problem>"}]}
Return {"findings": []} if you find nothing concrete. Do not flag stylistic choices,
omissions of minor data, or anything you are not reasonably confident about.
"""


@dataclass
class FinancialFinding:
    type: str
    claim: str
    explanation: str


@dataclass
class FinancialJudgment:
    findings: list[FinancialFinding] = field(default_factory=list)
    error: str | None = None


def judge_financial_consistency(
    source_facts: dict,
    brief_excerpt: str,
    model: str = DEFAULT_MODEL,
) -> FinancialJudgment:
    user = json.dumps({"source_facts": source_facts, "brief_excerpt": brief_excerpt[:20000]}, indent=2)
    try:
        result = chat_json(SYSTEM_PROMPT, user, model=model)
    except OllamaError as e:
        return FinancialJudgment(error=str(e))
    try:
        findings = [FinancialFinding(**f) for f in result.get("findings", [])]
        return FinancialJudgment(findings=findings)
    except TypeError as e:
        return FinancialJudgment(error=f"malformed judge response: {e}")
