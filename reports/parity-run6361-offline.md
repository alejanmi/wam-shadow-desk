# Shadow Brief diff · run 6361 · Annie · offline replay

6 checks reproduced the brief exactly; 11 findings; 0 failures.

## Findings and failures

| Severity | Check | Layer | What | Expected | Actual |
| --- | --- | --- | --- | --- | --- |
| high | `F-EARNINGS-COVERAGE` | L3 | Reader companies reporting this week missing from the earnings calendar | ["AMZN", "GOOG", "MSFT"] | {"calendar": ["AMZN"], "missing": ["MSFT 2026-10-28", "GOOG 2026-10-28"]} |
| high | `F-RATINGS-NEWS-DROPPED` | L3 | Rating upgrades/downgrades cut in favour of reiterations | every upgrade/downgrade in the 7-day window is shown | ["Loop Capital downgraded AAPL to Hold from Buy on 2026-10-20."] |
| medium | `F-FEED-MISSING` | L0 | News feeds that fetched but never reached the aggregator | [] | ["RSS Googlenews"] |
| medium | `F-SENSITIVITY-UNLINKED` | L3 | A reader's top-rated risk moved, and the brief did not connect them | brief references the reader's stated scenario when its driver moves >= 2% | [{"scenario": "Strait of Hormuz / Middle East Oil Shock", "concern": 8, "evidence": {"crudePct": 3.8202, "XLE": 2.6047, "XLE_rank": "best sector"}}] |
| medium | `F-STALE-AS-TODAY` | L1 | Rate tiles labelled 'today' carry an older reading | label shows the observation date (2026-10-22) | {"tiles": ["yield2Y", "yield10Y"], "observation": "2026-10-22", "published": "2026-10-24", "days_old": 2} |
| medium | `F-TICKER` | L1 | Reader tickers that no data source recognises | [] | {"profile": ["CITI: not a listed symbol; did you mean C?"], "quote_failures": ["CITI"]} |
| medium | `F-VIX-TWO-VALUES` | L1 | Two different VIX values on one page | one value per series per page | {"tile": 19.45, "text": 19.03} |
| low | `F-FUND-SECTOR` | L1 | Index funds classified as the Financial Services sector | funds looked through to their holdings (or excluded) | ["SCHD", "SPYM", "VOO", "VXF"] |
| low | `F-SECTOR-EXPOSURE` | L3 | Sectors the reader holds that the brief left out | ["Communication Services", "Consumer Discretionary", "Health Care", "Technology"] | {"shown": ["Communication Services", "Health Care", "Technology"], "omitted": ["Consumer Discretionary"], "omitted_moves": {"Consumer Discretionary": -1.6607}} |
| low | `F-STALE-GDPNOW` | L1 | GDPNow reading older than its freshness limit is still printed | <= 100 days old or omitted | 115 days old |
| low | `F-UNITS` | L1 | Yield changes written as percent instead of percentage points | -0.17 percentage points (17 bp) | ["tenyear_text"] |

### Detail and how to re-run each one

**`F-EARNINGS-COVERAGE`** (finding). The brief's own news text dates these reports inside the window, but Week Ahead lists only the calendar's names. Both cannot be right: either the FMP calendar missed them or the text is wrong. The live check (EDGAR 8-K item 2.02 after the date) settles it.

```
fixtures/run6361/brief_claims.json:earnings_mentions in window 2026-10-24..2026-10-31 minus reference_disclosures.json:earnings
```

**`F-RATINGS-NEWS-DROPPED`** (finding). The Processing node ranks news above reiterations only within one company, then sorts all companies by date and keeps 6, so an older downgrade loses to newer routine reiterations.

```
brief_facts.rating_changes_fixed(fixtures/run6361/raw_inputs.json:grades_since_2026_10_10, now=2026-10-24T21:39:53.379000+00:00)
```

**`F-FEED-MISSING`** (finding). RSS Aggregate runs once per inbound wire; it emitted before the Google News node finished.

```
fixtures/run6361/reference_disclosures.json:newsMeta.feedsMissing
```

**`F-SENSITIVITY-UNLINKED`** (finding). The workflow's Aggregate Sheets node drops the Sensitivity tab, so the model never sees it.

```
ReaderProfile.top_sensitivities(7) x fixtures/run6361/reference_market.json:price.commodities.crudePct, sectors.XLE
```

**`F-STALE-AS-TODAY`** (finding). Rate tiles labelled 'today' carry an older reading

```
fixtures/run6361/brief_claims.json:tiles[*].label == 'today' vs reference_market.json:fred.rateDate
```

**`F-TICKER`** (finding). The name is silently missing from every section of the brief (quotes, news, ratings, 13F).

```
ReaderProfile.ticker_issues(config/readers/annie.yaml) + fixtures/run6361/reference_market.json:price.quotesFailed
```

**`F-VIX-TWO-VALUES`** (finding). Two different VIX values on one page

```
fixtures/run6361/brief_claims.json:tiles.vix vs text_numbers[vix]  (tile=FMP ^VIX quote, text=FRED VIXCLS 2026-10-22)
```

**`F-FUND-SECTOR`** (finding). FMP's profile sector for an ETF is the issuer's industry; any sector exposure built on it is wrong.

```
fixtures/run6361/reference_disclosures.json:sectorMapping[fund tickers]
```

**`F-SECTOR-EXPOSURE`** (finding). Sectors the reader holds that the brief left out

```
holdings minus funds -> fixtures/run6361/reference_disclosures.json:sectorMapping -> SPDR sector; vs brief_claims.json:sector_exposure_shown
```

**`F-STALE-GDPNOW`** (finding). The page discloses the age, but a 116-day-old nowcast is not a current GDP read; suppress or refresh.

```
fixtures/run6361/brief_claims.json:text_numbers[gdpNow].as_of; limit MAX_AGE_DAYS['quarterly']=100
```

**`F-UNITS`** (finding). 'fell 0.17%' reads as a 0.17% relative move (about 0.8 bp).

```
fixtures/run6361/brief_claims.json:text_numbers[unit_written=='%' and series startswith 'yield']
```

## Reproduced without n8n

| Check | Layer | What | Query |
| --- | --- | --- | --- |
| `P-BREADTH` | L2 | Breadth of the reader's companies | `brief_facts.breadth(fixtures/run6361/reference_market.json:price.quotes)` |
| `P-MOVERS` | L2 | Biggest riser and faller | `brief_facts.top_movers(fixtures/run6361/reference_market.json:price.quotes)` |
| `P-SECTORS` | L2 | Best and worst SPDR sector of the session | `brief_facts.sector_summary(fixtures/run6361/reference_market.json:sectors)` |
| `P-SRO` | L2 | S&P 500 regime signal (EMA10 vs EMA35) | `brief_facts.sro(fixtures/run6361/raw_inputs.json:gspc_newest_first reversed)` |
| `P-RSI` | L2 | Average RSI-14 across holdings | `brief_facts.rsi_summary(fixtures/run6361/reference_disclosures.json:rsi)` |
| `P-RATINGS` | L2 | Analyst rating actions shown (port of the Processing node) | `brief_facts.rating_changes(fixtures/run6361/raw_inputs.json:grades_since_2026_10_10, now=2026-10-24T21:39:53.379000+00:00)` |
