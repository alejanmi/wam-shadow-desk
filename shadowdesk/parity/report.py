"""Render parity checks as the first version of the Shadow Brief diff."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from shadowdesk.parity.checks import Check

_SEV = {"high": 0, "medium": 1, "low": 2, "info": 3}


def _fmt(v) -> str:
    if v is None:
        return "—"
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s.replace("|", "\\|").replace("\n", " ")


def render_markdown(title: str, checks: list[Check]) -> str:
    findings = sorted((c for c in checks if c.status in {"finding", "fail"}), key=lambda c: (_SEV[c.severity], c.check_id))
    passes = [c for c in checks if c.status == "pass"]
    n = {s: sum(c.status == s for c in checks) for s in ("pass", "finding", "fail", "skipped")}
    lines = [f"# {title}", "",
             f"{n['pass']} checks reproduced the brief exactly; {n['finding']} findings; {n['fail']} failures.", "",
             "## Findings and failures", "",
             "| Severity | Check | Layer | What | Expected | Actual |", "| --- | --- | --- | --- | --- | --- |"]
    for c in findings:
        lines.append(f"| {c.severity} | `{c.check_id}` | {c.layer} | {_fmt(c.title)} | {_fmt(c.expected)} | {_fmt(c.actual)} |")
    lines += ["", "### Detail and how to re-run each one", ""]
    for c in findings:
        lines += [f"**`{c.check_id}`** ({c.status}). {c.detail or c.title}", "", f"```\n{c.query}\n```", ""]
    lines += ["## Reproduced without n8n", "", "| Check | Layer | What | Query |", "| --- | --- | --- | --- |"]
    for c in passes:
        lines.append(f"| `{c.check_id}` | {c.layer} | {_fmt(c.title)} | `{_fmt(c.query)}` |")
    return "\n".join(lines) + "\n"


def write_reports(out_dir: str | Path, name: str, title: str, checks: list[Check]) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md, js = out / f"{name}.md", out / f"{name}.json"
    md.write_text(render_markdown(title, checks), encoding="utf-8")
    js.write_text(json.dumps([asdict(c) for c in checks], indent=2, default=str), encoding="utf-8")
    return md, js
