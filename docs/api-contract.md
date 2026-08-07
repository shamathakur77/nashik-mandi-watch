# API Contract — data.gov.in Daily Mandi Prices

**Resource:** `9ef84268-d588-465a-a308-a864a43d0070` — "Current Daily Price of Various Commodities from Various Markets (Mandi)"
**Upstream:** AGMARKNET, via Ministry of Agriculture and Farmers Welfare
**Verified:** 2026-08-07, live responses fetched in-browser with the public sample key (10-record cap), `filters[state.keyword]=Maharashtra&filters[district]=Nashik`, at `offset=0` (~13:45 IST) and `offset=10` (~14:45 IST). Raw responses archived at `data/raw/fixtures/2026-08-07-sample-key-nashik.json` and `...-offset10.json`.

Every field name, date format, and market string used in this repo's code MUST trace to this file. If a live response ever contradicts this file, update this file first, then the code.

## Endpoint & auth

| Item | Value | Status |
|---|---|---|
| Base URL | `https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070` | ✅ verified |
| Auth | query param `api-key` | ✅ verified |
| Sample key | `579b464d...571b` — still active, hard-capped at 10 records per call (`limit=10` honored, higher values clamp) | ✅ verified (cap observed: `count: 10` vs `total: 15`) |
| Real key | GitHub secret `DATA_GOV_IN_KEY` | ⏳ to verify at Loop 1 start |
| Format | `format=json` | ✅ verified |
| Pagination | `limit` + `offset` (echoed back as **strings**: `"limit": "10", "offset": "0"`); `total` and `count` are **numbers** | ✅ verified for limit/offset echo; offset paging itself ⏳ provisional until tested |

## Filter syntax — verified, with one landmine

- `filters[state.keyword]=Maharashtra` — ✅ works; state is exposed for filtering as `state.keyword` (per `field_exposed`), NOT plain `state`
- `filters[district]=Nashik` — ✅ works as an effective exact filter for single-token values (all returned records were district=Nashik)
- ⚠️ **`filters[market]=...` is NOT an exact filter for multi-word values — VERIFIED BROKEN for our purpose.** `filters[market]=Lasalgaon(Niphad) APMC` returned `total: 473` relevance-ranked records spanning ALL Maharashtra districts (Sangli, Nagpur, Palghar, Jalna, ...) — the backend (Elasticsearch) treats the value as a loose token match ("APMC" matches every market), merely ranking the true Lasalgaon records first. Fixture: `data/raw/fixtures/2026-08-07-sample-key-market-filter-test.json`.
  **Rule for all code: never filter by market server-side. Fetch by `district` (and `commodity` where needed) and select markets client-side.**
- Exposed filterable fields (from `field_exposed`): `state.keyword`, `district`, `market`, `commodity`, `variety`, `grade`
- `arrival_date` is NOT in `field_exposed` → date-range filtering is presumed unsupported; ⏳ verify in Loop 1 before relying on it
- Useful scale number: all-Maharashtra current-day total was **473** records at ~15:00 IST → with the real key, `limit=1000` should fetch the whole state in one page; Nashik alone is a few dozen rows.

## Record schema (verified against live records)

| id (use this in code) | Display name | JSON type observed | Example |
|---|---|---|---|
| `state` | State | string | `"Maharashtra"` |
| `district` | District | string | `"Nashik"` |
| `market` | Market | string | `"Lasalgaon(Niphad) APMC"` |
| `commodity` | Commodity | string | `"Onion"` |
| `variety` | Variety | string | `"Unhali"` |
| `grade` | Grade | string | `"Local"`, `"FAQ"`, `"Non-FAQ"` |
| `arrival_date` | Arrival_Date | string | `"07/08/2026"` |
| `min_price` | Min_x0020_Price | **number** (double) | `800` |
| `max_price` | Max_x0020_Price | **number** (double) | `2500` |
| `modal_price` | Modal_x0020_Price | **number** (double) | `2150` |

Prices are ₹ per quintal, returned as JSON numbers — no string casting needed, but code should still coerce defensively (`float()`).

## arrival_date format — VERIFIED

`"07/08/2026"` fetched on 7 August 2026 → **`DD/MM/YYYY`**. Parse with `datetime.strptime(s, "%d/%m/%Y")`. Never assume ISO. (Raw JSON escapes slashes as `\/`; any real JSON parser handles this — do not regex the raw text.)

## Market names — the big Loop 0 finding

Nashik market strings carry an **` APMC` suffix**, and sub-yards are in parentheses *before* the suffix. Confirmed exact strings from live data (2026-08-07):

- `Lasalgaon(Niphad) APMC` — **onion, confirmed live** (modal ₹2150/q)
- `Pimpalgaon Baswant APMC`
- `Pimpalgaon Baswant(Saykheda) APMC`
- `Devala APMC`
- `Ghoti APMC`
- `Nasik APMC` — ⚠️ note spelling: the city market is **"Nasik"** while the district field is `"Nashik"`. Never filter markets by the substring "Nashik".

- `Lasalgaon(Vinchur) APMC` — **onion, confirmed live** (min 600 / max 2525 / modal ₹2150/q) via the relevance-ranked market-filter test

⏳ **PROVISIONAL:** the main Lasalgaon yard is presumed to appear as `Lasalgaon APMC` — **string still not observed live.** Suggestive but not conclusive: in the relevance-ranked test, Niphad and Vinchur topped the results while no plain `Lasalgaon APMC` appeared; it may simply not have reported by mid-afternoon today. Close this at Loop 1 by pulling ALL Nashik records with the real key and listing distinct market strings. Until then, code must select Lasalgaon yards by **prefix match `market.startswith("Lasalgaon")`**, never by exact string equality to an unconfirmed name, and the card's headline must use the best available Lasalgaon yard (priority: main yard if it exists → Niphad → Vinchur), always printing which yard it used.

## Onion specifics (verified)

- Commodity string: `"Onion"` (exact)
- Variety observed in season: `"Unhali"` (summer/rabi crop), grade `"Local"`
- Same market can plausibly report multiple variety/grade rows → dedupe key must include variety (+ grade for safety): `market + commodity + variety + grade + arrival_date`

## Data depth & freshness — CRITICAL provisional findings

1. **Snapshot resource, likely no history:** `total: 15` for all of Nashik district on the current date strongly suggests this resource holds only the **current day's** prices (title says "Current Daily Price"). Backfill from this resource is presumed **impossible**. ⏳ Verify in Loop 1 (query without date assumptions using the real key); if confirmed, `data/history.csv` builds forward from day 1 and this limitation is recorded here as final.
2. **Refresh timing risk:** response metadata showed `updated_date: 2026-08-07T08:00:48Z` (= **13:30 IST**), yet the planned cron is 04:00 UTC (09:30 IST). Today's records may have landed *after* the planned cron time. ⏳ Loop 4 must reconsider the schedule (candidate: ~10:00 UTC / 15:30 IST, or a twice-daily cron) based on what the real key returns at those hours. A too-early cron silently produces stale/empty pulls — the fetcher must fail loudly on zero records for the expected date.
3. **Sundays/holidays:** markets report trading days only; gaps are expected and must not be treated as errors.
4. **The index mutates intraday — VERIFIED:** between the offset=0 call (~13:45 IST, `total: 15`, `updated_date 08:00:48Z`) and the offset=10 call (~14:45 IST, `total: 26`, `updated_date 09:01:02Z`), 11 new Nashik records landed. Consequences, all mandatory for `fetch_mandi.py`:
   - Paginating a mutating index shifts records across pages: **4 records appeared on BOTH pages** (Devala Bajra & Maize, Ghoti Cucumbar & Cauliflower). Dedupe on `market+commodity+variety+grade+arrival_date` is not optional.
   - A single early pull undercounts the day. Fetch as late as practical and/or re-pull; last write wins per dedupe key (prices for a key may also be revised intraday).
   - Re-read `total` after the final page; if it grew during pagination, do one more sweep.

## Access-path constraints (environment findings, 2026-08-07)

- Claude's cloud sandbox **cannot** reach `api.data.gov.in` (egress allowlist blocks direct connections; the fetch-service path gets HTTP 400 from the API — the host appears to reject non-browser/cloud fetchers). All Loop 0 verification therefore ran through Shama's browser.
- ⚠️ Untested risk: whether **GitHub Actions runner IPs** can reach the API. Must be the first thing Loop 4's `workflow_dispatch` dry run proves. If blocked, fallback options: self-hosted runner, or a different scheduler — decide only if it fails.
- Local self-tests in Loops 1–3 run against archived fixtures + pasted live responses (`data/raw/fixtures/`), not live calls from the sandbox.

## Open items before this contract is final

| # | Item | Closes at |
|---|---|---|
| 1 | ~~Inspect further pages / market-filter variants for Lasalgaon yards~~ **CLOSED**: `Lasalgaon(Vinchur) APMC` confirmed; market filter proven unusable; main `Lasalgaon APMC` string remains unobserved | Loop 0 ✅ |
| 2 | Full distinct-market list for Nashik with real key (closes the main-yard question) | Loop 1 start |
| 3 | Confirm whether any historical `arrival_date` is servable (backfill feasibility) | Loop 1 |
| 4 | Confirm GitHub Actions runners can reach the API | Loop 4 |
| 5 | Confirm data refresh time → set cron accordingly | Loop 4 |

## Loop 0 sign-off

Verified live on 2026-08-07 through 3 browser fetches (fixtures archived). Field ids, `DD/MM/YYYY` dates, numeric prices, district filtering, APMC-suffixed market names, intraday index mutation, and the market-filter landmine are all evidence-backed. Remaining ⏳ items are assigned to their loops above.
