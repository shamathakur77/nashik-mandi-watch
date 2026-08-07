# nashik-mandi-watch

Zero-cost daily pipeline: wholesale mandi prices for **Nashik district (onion
focus, Lasalgaon)** from India's Open Government Data API → price-move detection
→ a bilingual (मराठी + English) shareable daily card. No servers, no paid
services — GitHub Actions + this repo are the whole system.

**Every field name, date format and market string in this code traces to
[`docs/api-contract.md`](docs/api-contract.md)** — verified against live API
responses on 2026-08-07. Read that file before changing anything.

## The daily card

Rendered at 09:30 IST and refreshed at 15:30 IST every market day:

**Stable URL (for Tejas / WhatsApp / anywhere):**

```
https://raw.githubusercontent.com/shamathakur77/nashik-mandi-watch/main/reports/latest-card.png
```

Bookmark it on the phone — it always shows the newest card. Archive lives in
`reports/cards/YYYY-MM-DD.png`. Machine-readable data contract:
`reports/latest.json`.

## How it works

| Step | Script | Output |
|---|---|---|
| 1. Fetch | `fetch_mandi.py` | `data/raw/YYYY-MM-DD.json`, `data/history.csv` (deduped, last-write-wins) |
| 2. Analyze | `analyze.py` | `reports/latest.json` — per-market onion stats vs 7/30-trading-day averages, top movers, bilingual verdicts |
| 3. Card | `make_card.py` | `reports/cards/YYYY-MM-DD.png` + `reports/latest-card.png` (1080×1350) |

Signal rules: **ALERT** = ±10% vs 7-day average, **NOTABLE** = ±5%, else
STEADY. A market with fewer than 7 prior trading days is **BASELINE** — no
percentage is ever computed against a partial window; the card says "building
baseline" in both languages instead. The upstream resource serves **current-day
data only** (verified), so history accumulates forward from 2026-08-07.

## One-command local run

```bash
pip install -r requirements.txt
DATA_GOV_IN_KEY=your_key python fetch_mandi.py && python analyze.py && python make_card.py
```

Offline (no network/key — replays a saved pull):

```bash
python fetch_mandi.py --from-file data/raw/2026-08-07.json && python analyze.py && python make_card.py
```

## Automation

`.github/workflows/daily.yml` runs the chain at 04:00 + 10:00 UTC (09:30 +
15:30 IST) and commits results. `workflow_dispatch` allows on-demand runs from
the Actions tab. Runs never overlap (concurrency group). Failures are loud —
a red run means the API broke or returned nothing.

## Troubleshooting

| Symptom | Meaning / fix |
|---|---|
| Red run on Sunday / holiday | Normal — mandis closed, zero records, fetch fails loudly by design |
| Red run on a weekday | Open the run log: HTTP errors → data.gov.in hiccup, re-run the workflow; zero records at 09:30 → data not in yet, the 15:30 run will catch it |
| Card missing a market | Market didn't report that day — check `reports/latest.json` → `onion_markets` |
| "BASELINE" instead of % | Fewer than 7 trading days of history for that market — arrows appear ~2 weeks after first data |
| Marathi looks broken locally | Pillow needs raqm shaping: `pip install --upgrade Pillow` (CI wheels have it) |

## Manual setup (already done / one-time)

1. Create this repo (public).
2. Add repo secret `DATA_GOV_IN_KEY` (Settings → Secrets → Actions).
3. Actions enabled by default — nothing else. Fonts (Noto Sans Devanagari,
   OFL-licensed) are bundled in `assets/`.

Source: **AGMARKNET via data.gov.in** · resource `9ef84268-d588-465a-a308-a864a43d0070`.
WhatsApp auto-sending is deliberately out of scope for v1 — share the stable
URL by hand.
