"""Default-deny policy for local models.

This is metadata validation only. Acquisition, scanning, promotion, and
Ollama administration remain operator-only activities outside the agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PolicyViolation:
    field: str
    message: str


def validate_model_entry(entry: dict[str, Any]) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []
    source = entry.get("source") or {}
    if entry.get("format") not in {"gguf", "safetensors"}:
        violations.append(PolicyViolation("format", "only GGUF or safetensors models are admitted"))
    if not source.get("revision") or len(str(source["revision"])) != 40:
        violations.append(PolicyViolation("source.revision", "a full 40-character commit SHA is required"))
    if not source.get("sha256") or len(str(source["sha256"])) != 64:
        violations.append(PolicyViolation("source.sha256", "a 64-character SHA256 is required"))
    if entry.get("trust_remote_code") is True:
        violations.append(PolicyViolation("trust_remote_code", "remote code execution is forbidden"))
    scanners = entry.get("scanners") or {}
    for scanner in ("picklescan", "protectai", "jfrog"):
        if scanners.get(scanner) != "pass":
            violations.append(PolicyViolation(f"scanners.{scanner}", "required scanner must pass"))
    if entry.get("template_reviewed") is not True:
        violations.append(PolicyViolation("template_reviewed", "chat template review is required"))
    return violations
