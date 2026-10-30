# Borrowed ideas

This repo shares no code, data, prompts or memory with Nico's `research-direction-scout`.
When an idea from another project is re-implemented here, record it below.

| Idea | Source | Where it lives here |
| --- | --- | --- |
| Fixed budget, single metric, keep-or-revert loop discipline | karpathy/autoresearch | phase exit tests (`docs/STRATEGY.md`) |
| Detect -> Diagnose -> Intervene -> Verify -> Learn, honest `passed=None` | AutoDetections_Santino (ported, not borrowed) | `shadowdesk/reliability/` |
| Bounded experiments + JSON experiment records | AutoDetections_Santino / NewARLoopLocal | `shadowdesk/ledger/bounded.py`, `experiment_record.py` |
| Four falsification null levels | Echoes & Shadows (Ale) | N1-N4, plus N5 for markets |
