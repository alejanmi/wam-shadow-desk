"""The inquiry record: every claim the loop makes carries how it was checked.

A claim's verdict is computed from the layers it passed, never set by hand, so
a model cannot promote its own conclusion. See docs/STRATEGY.md for the layer
definitions (L0 provenance ... L7 outcome) and the null levels N1-N5.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum


class Verdict(str, Enum):
    VERIFIED = "Verified"      # L0-L4 passed, outcome (L7) pending
    SUPPORTED = "Supported"    # + L5 causal identification passed
    CONTESTED = "Contested"    # red team (L6) not clearly beaten
    JAGGED = "Jagged"          # models disagree beyond threshold on L3/L6
    REFUTED = "Refuted"        # failed a null or a check
    UNTESTABLE = "Untestable"  # no null could be stated: logged, never shown as a finding
    FACT = "Fact"              # deterministic data check (L0-L2 only), no hypothesis involved


LAYERS = ("L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7")
NULLS = ("N1", "N2", "N3", "N4", "N5")
JAGGED_AGREEMENT = 0.7  # below this cross-model agreement, the claim is Jagged


@dataclass
class InquiryRecord:
    claim_id: str
    statement: str
    queries: list[str]                         # exact re-runnable calls / prompts (with hashes) behind the claim
    layers_passed: list[str] = field(default_factory=list)
    failed_at: str | None = None               # e.g. "N3" or "L1"
    rivals: list[str] = field(default_factory=list)
    nulls: dict[str, float | None] = field(default_factory=dict)   # p-values; None = not run
    model_agreement: float | None = None
    red_team_beaten: bool | None = None
    hypothesis: bool = True                    # False for deterministic data checks
    forecast: dict | None = None               # {"p":..., "resolves":"YYYY-MM-DD", "metric":...}
    data_refs: list[str] = field(default_factory=list)   # Provenance.ref() strings

    def __post_init__(self):
        if not self.queries:
            raise ValueError("an inquiry must record at least one query")
        bad = [l for l in self.layers_passed if l not in LAYERS]
        if bad:
            raise ValueError(f"unknown layers {bad}")

    @property
    def verdict(self) -> Verdict:
        if self.failed_at:
            return Verdict.REFUTED
        if not self.hypothesis:
            return Verdict.FACT if {"L0", "L1", "L2"} <= set(self.layers_passed) else Verdict.UNTESTABLE
        if not any(v is not None for v in self.nulls.values()):
            return Verdict.UNTESTABLE
        if self.model_agreement is not None and self.model_agreement < JAGGED_AGREEMENT:
            return Verdict.JAGGED
        if self.red_team_beaten is False:
            return Verdict.CONTESTED
        if {"L0", "L1", "L2", "L3", "L4", "L5"} <= set(self.layers_passed):
            return Verdict.SUPPORTED
        if {"L0", "L1", "L2", "L3", "L4"} <= set(self.layers_passed):
            return Verdict.VERIFIED
        return Verdict.UNTESTABLE

    def to_json(self) -> str:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return json.dumps(d, indent=2, sort_keys=True)
