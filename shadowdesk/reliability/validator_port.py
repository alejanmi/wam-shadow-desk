"""Python port of the n8n "Validator" Code node.

The source of truth is the actual jsCode on the Validator node inside
"Santi Miguel AI Agent (F).json" (node id d5cd5540-41bd-4d2d-aa98-9354b5154646).
This port exists so the detection/verification loop can run offline
(without a Node.js runtime) against replayed or synthetic brief text.

If the Validator node's jsCode changes in the n8n workflow, this file must
be updated to match — it is a manual port, not a shared implementation.
"""

from __future__ import annotations

import re

from shadowdesk.reliability.trace import ValidatorResult

SECTION_IDS = ["desk", "spotlight", "situations", "clients", "analyst", "people", "scenarios", "week"]

REQUIRED_MARKERS = ["perf-here", "movers-here", "sectors-here"]

DEAD_ELEMENTS = ["tactical-read", "macro-overview", "sec-lead", "fd-b", "<details", "<script", "<style"]

PLACEHOLDER_RE = re.compile(
    r"\[(TICKER|Tool|TBD|Name|Event|House|URL|Publication|Setup|Punchline|Claim|Step)[^\]]*\]"
)
PREAMBLE_RE = re.compile(r'^\s*<div class="sec-num" id="desk">01</div>')


def _count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text))


DEFAULT_THRESHOLDS = {
    "chars_min": 40000,
    "chars_max": 140000,
    "pbItems": 5,
    "mv": 3,
    "blind": 1,
    "ap": 3,
    "secNews": 2,
}


def run_validator(text: str, usage: dict | None = None, thresholds: dict | None = None) -> ValidatorResult:
    """`thresholds` overrides one or more of DEFAULT_THRESHOLDS — used to verify
    a tighten_validator_threshold/loosen_validator_threshold intervention offline
    without re-executing the patched jsCode (see wam/verification.py)."""
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    failures: list[str] = []
    warnings: list[str] = []

    # 1. Eight sections, canonical order, exact ids.
    positions = [text.find(f'<div class="sec-num" id="{i}">') for i in SECTION_IDS]
    missing = [sid for sid, pos in zip(SECTION_IDS, positions) if pos == -1]
    for sid in missing:
        (warnings if sid == "clients" else failures).append(f"missing section: {sid}")
    present = [p for p in positions if p != -1]
    for i in range(1, len(present)):
        if present[i] < present[i - 1]:
            failures.append("sections out of canonical order")
            break

    # 2. Joke block / truncation tripwire.
    jokes = _count(r'<div class="jokes">', text)
    if jokes != 1:
        failures.append(f"joke block count = {jokes} (expected 1)")
    tail = text[-600:]
    if "joke-a" not in tail:
        failures.append("output does not end at the joke block (probable truncation)")

    # 3. Engine markers.
    for m in REQUIRED_MARKERS:
        if f'<div class="{m}"' not in text:
            failures.append(f"missing marker: {m}")
    if '<div class="consensus-here"' not in text:
        warnings.append("missing marker: consensus-here (fine in advisor mode)")

    # 4. Counted contracts.
    pb_wrap = _count(r'<div class="pb">', text)
    if pb_wrap != 1:
        failures.append(f"pb wrapper count = {pb_wrap} (expected 1)")
    pb_items = _count(r'<div class="pb-item">', text)
    if pb_items != t["pbItems"]:
        failures.append(f"pb-item count = {pb_items} (expected {t['pbItems']})")
    mv = _count(r'<div class="mv-item">', text)
    if mv != t["mv"]:
        warnings.append(f"mv-item count = {mv} (expected {t['mv']})")
    blind = _count(r'<div class="bsx-top-banner">', text)
    if blind != t["blind"]:
        failures.append(f"blind spot count = {blind} (expected {t['blind']})")
    ap = _count(r'<div class="ap-item">', text)
    if ap != t["ap"]:
        warnings.append(f"ap-item count = {ap} (expected {t['ap']})")
    sec_news = _count(r'<div class="sec-news"', text)
    if sec_news != t["secNews"]:
        warnings.append(f"sec-news count = {sec_news} (expected {t['secNews']})")
    on_items = _count(r'<div class="on-item">', text)
    if on_items < 3 or on_items > 8:
        warnings.append(f"on-item count = {on_items}")
    s60 = _count(r'<x-dd class="dd s60">', text)
    if s60 != 1:
        warnings.append(f"Section 01 drawer count = {s60} (expected 1)")

    # 5. Mechanical bans.
    em_dash = text.count("—")
    if em_dash > 0:
        failures.append(f"em dashes: {em_dash}")
    amp = text.count("&amp;")
    if amp > 0:
        warnings.append(f"&amp; entities: {amp} (engine sweeps these; count is a quality signal)")
    for d in DEAD_ELEMENTS:
        if d in text:
            failures.append(f"forbidden element: {d}")

    # 6. Placeholders that reached the page.
    ph = PLACEHOLDER_RE.findall(text)
    if ph:
        # findall on a group returns the captured group only; re-run fullmatch to report the literal text
        full = PLACEHOLDER_RE.finditer(text)
        seen: list[str] = []
        for m in full:
            if m.group(0) not in seen:
                seen.append(m.group(0))
            if len(seen) >= 5:
                break
        failures.append("placeholders on page: " + ", ".join(seen))
    if "DIRECT_URL" in text:
        failures.append("DIRECT_URL placeholder in a must-read")

    # 7. Size sanity.
    chars = len(text)
    if chars < t["chars_min"]:
        failures.append(f"output too short: {chars} chars")
    if chars > t["chars_max"]:
        warnings.append(f"output long: {chars} chars")

    # 8. Preamble check.
    if not PREAMBLE_RE.match(text):
        failures.append("output does not start at the Section 01 marker (preamble or narration present)")

    usage = usage or {}
    stats = {
        "chars": chars,
        "sections": len(present),
        "pbItems": pb_items,
        "mv": mv,
        "blind": blind,
        "ap": ap,
        "secNews": sec_news,
        "onItems": on_items,
        "jokes": jokes,
        "emDash": em_dash,
        "amp": amp,
        "promptTokens": usage.get("promptTokens", usage.get("prompt_tokens")),
        "completionTokens": usage.get("completionTokens", usage.get("completion_tokens")),
        "reasoningTokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        if usage.get("completion_tokens_details")
        else usage.get("reasoningTokens"),
    }

    return ValidatorResult(ok=len(failures) == 0, failures=failures, warnings=warnings, stats=stats)
