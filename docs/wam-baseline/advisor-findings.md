# Findings

Static review of the exported workflow (83 nodes), the system prompt
(`extracted/system-prompt.txt`, ~168K characters / 1300 lines), the user-message
template (`extracted/user-message-template.txt`), and the JS in the Code nodes
(`extracted/code/`). Ranked by impact. All of these were found by reading the
actual node configs and code, not by running the workflow — the one baseline
execution attempted so far (id `5187`) failed immediately on a missing credential
(see `HANDOFF.md`), before reaching any of this logic.

---

## 1. The QA gate is dead code — the biggest risk

`Validator` (`extracted/code/validator.js`) is a real, careful QA pass: it checks
that all eight sections are present and in canonical order, that the joke block
exists (used as a truncation tripwire), that the engine markers (`perf-here`,
`movers-here`, `sectors-here`) are present, that counted elements match their
contract (exactly 5 `pb-item`s, exactly 3 `mv-item`s, exactly 1 blind spot, etc.),
that there are zero em dashes, that no forbidden elements or placeholder tokens
(`[TICKER]`, `DIRECT_URL`, etc.) leaked into the output, and that output length is
sane (40K–140K characters). It returns `{ ok, failures, warnings, stats, output }`.

**Nothing in the workflow reads `ok`.** The entire 83-node graph has zero
`n8n-nodes-base.if` or `.switch` nodes (confirmed by listing every distinct node
`type` in the workflow — see `workflows/production/santi-miguel-ai-agent.json`).
`Validator`'s two outgoing connections (`Validator → strip text1` and
`Validator → Formatting2`) both fire unconditionally regardless of `ok`. A brief
that fails every check in the file still gets turned into a podcast and emailed.

**Fix:** add an IF node right after `Validator` on `{{ $json.ok }}`. True branch:
continue to `strip text1` / `Formatting2` as today. False branch: send an internal
alert (to the operator, not the client-facing send) with `$json.failures` and
`$json.warnings`, and stop — do not proceed to podcast generation or email.

---

## 2. Hedge Fund Flow section is fed the wrong data shape

The system prompt's Section 05 "(2) HEDGE FUND FLOW" block
(`extracted/system-prompt.txt`, search `RENDER FROM smartMoney`) is written
entirely against a structured object: `smartMoney.hasData`, `smartMoney.period`,
`smartMoney.periodFull`, and `smartMoney.rows[]` where each row has `symbol`,
`isFund`, and a prewritten `line` to be rendered **verbatim**.

`13F Processing` (`extracted/code/13f-processing.js`, around line 287) does build
exactly that shape:

```js
return [{ json: {
  smartMoney: {
    hasData: hasData, period: periodShort, periodFull: periodStr,
    ...
  },
  smartMoneySummary: hasData ? summaryParts.join("\n") : "",
  ...
}}];
```

But the user-message template (`extracted/user-message-template.txt`, line ~231)
only interpolates the flat string:

```
=== 13F INSTITUTIONAL SMART MONEY (last-quarter filings, Hedge Fund Flow) ===

{{ $json.smartMoneySummary }}
```

`$json.smartMoney` (the structured object the prompt's render instructions
require) never appears anywhere in the user message. It's computed by
`13F Processing`, survives the merge chain as far as whatever feeds `Edit Fields`,
and is then simply never referenced when the message is assembled — confirmed by
grepping the full user-message template for `smartMoney` and `hasData`: only
`smartMoneySummary` appears, under a differently-named header.

Practical effect: every brief's Hedge Fund Flow subsection is being written by the
model from a prose summary instead of the exact rows the prompt strictly demands,
which risks either fabricated per-row structure (against the prompt's own
"NUMBER PROVENANCE" rule) or silent omission of the whole block.

**Fix:** add a block to the user-message template that passes the structured
object through, e.g.:

```
=== HEDGE FUND FLOW (smartMoney) ===

{{ JSON.stringify($json.smartMoney || { hasData: false }) }}
```

placed so it's clearly the block the prompt's Section 05 (2) instructions refer
to by name.

---

## 3. NYT (and other sources) are recognized but never fetched

`RSS Aggregate` (`extracted/code/rss-aggregate.js`) has `TIER` and `PUBLISHER`
maps (lines ~65–72 and ~134–145) that already know about `nytimes.com`,
`apnews.com`, `barrons.com`, `bloomberg.com`, `axios.com`, `politico.com`, and
`calculatedriskblog.com`. None of them are actually fetched: the `NODES` array
(line ~31) that lists which RSS feed nodes to pull from only contains:

```
RSS WSJ Markets, RSS WSJ Economy, RSS WSJ Tech, RSS FedFeeds, RSS Oilprice1,
RSS FedRes1, RSS Seeking Alpha, RSS DOW/WSJ1, RSS CNBC1, RSS MARKETWATCH,
RSS FT, RSS Googlenews
```

— confirmed against the actual `rssFeedRead` node URLs in the exported workflow.
There is no NYT (or AP, Barron's, Bloomberg) feed node on the canvas at all.

**Fix:** add an RSS Feed Read node for NYT (e.g. `https://rss.nytimes.com/services/xml/rss/nyt/Business.xml`
and/or the DealBook feed `https://rss.nytimes.com/services/xml/rss/nyt/dealbook.xml`),
wire it the same way every other RSS node is wired (`O aggregate → RSS NYT ... →
RSS Aggregate`), and add its node name to the `NODES` array in `rss-aggregate.js`.
No other code change needed — tiering/publisher-name lookup already works once the
node exists.

---

## 4. Pre-flight payload check was written but never deployed

The bottom half of `extracted/code/validator.js` (from the `NODE B · PRE-FLIGHT
PAYLOAD CHECK` comment onward) is a complete, working check: holdings present,
`advisorName` present, `newsContext` has at least 20 items, `macroContext` has at
least 10 series, payload is at least ~150K characters, etc. It is **commented
out** and is not a real node anywhere in the 83-node workflow (confirmed: no node
named "Pre-Flight" or similar exists).

Practical effect: if an upstream data source fails silently (an empty Google
Sheets read, a data API returning nothing), the workflow still runs the full,
~30-minute, 32K-max-token DeepSeek generation call before anything notices the
input was broken.

**Fix:** paste the commented block into a real Code node placed before `Edit
Fields` (right after the point where all the data-gathering branches have merged
back together), followed by an IF node on `{{ $json.preflight.ok }}` — false
branch alerts and stops, same pattern as finding #1.

---

## 5. Orphaned agent node

`WM_AGENT_OG` is a fully configured `@n8n/n8n-nodes-langchain.agent` node with
both an Anthropic and a DeepSeek chat model attached (together ~200KB of
config). Listing every connection in the workflow shows it has exactly two
incoming `ai_languageModel` edges and **zero** `main` connections in or out —
it is not wired into the pipeline at all. The workflow actually generates the
brief via a plain HTTP request to DeepSeek's chat completions endpoint (the
`DeepSeek` node), not through this agent node.

This looks like a leftover from an earlier tool-calling-agent architecture that
was abandoned in favor of the current single-shot HTTP approach.

**Status:** disabled (`"disabled": true`) in the TEST copy so it can't
accidentally run if it ever gets reconnected by mistake. Left in place rather
than deleted, in case it's wanted for reference. Production is untouched.

---

## Not yet checked

- Whether other structured-vs-summary mismatches like #2 exist elsewhere in the
  user-message template — only `smartMoney` was checked in depth. A systematic
  pass would grep every `=== BLOCK NAME ===` header's binding against what each
  upstream Code node actually emits.
- Whether the retry-on-fail settings on `DeepSeek` (HTTP-level retry, 2 tries)
  interact badly with the 30-minute per-call timeout during a real incident.
- End-to-end behavior once a real run succeeds — no execution has completed yet
  (see `HANDOFF.md` for the credential-restoration step blocking this).
