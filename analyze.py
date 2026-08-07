#!/usr/bin/env python3
"""
analyze.py — signal detection for nashik-mandi-watch.

Reads data/history.csv (built by fetch_mandi.py), computes onion price moves
per Nashik market vs 7- and 30-trading-day rolling averages, flags moves,
and writes reports/latest.json with bilingual (English + Marathi) verdicts.

Rules (from the project spec + docs/api-contract.md):
  - Rolling windows use AVAILABLE trading dates, never calendar days.
  - ALERT  : |move vs 7-day avg| > 10%
  - NOTABLE: |move vs 7-day avg| > 5%
  - STEADY : otherwise
  - BASELINE (cold start): a market with fewer than 7 PRIOR trading days gets
    no % comparison at all — never a partial window, never a fake 0%.
  - Headline yard priority: Lasalgaon APMC -> Lasalgaon(Niphad) APMC ->
    Lasalgaon(Vinchur) APMC (prefix-matched, contract rule), labeled.
  - A market+date can carry several variety/grade rows; the market's daily
    price is the MEDIAN modal across those rows (simple, robust, explainable).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

HISTORY = os.path.join("data", "history.csv")
OUT = os.path.join("reports", "latest.json")
DISTRICT = "Nashik"
ONION = "Onion"
IST = timezone(timedelta(hours=5, minutes=30))

WINDOW_7, WINDOW_30 = 7, 30
ALERT_PCT, NOTABLE_PCT = 10.0, 5.0

MARATHI_MONTHS = {1: "जानेवारी", 2: "फेब्रुवारी", 3: "मार्च", 4: "एप्रिल",
                  5: "मे", 6: "जून", 7: "जुलै", 8: "ऑगस्ट",
                  9: "सप्टेंबर", 10: "ऑक्टोबर", 11: "नोव्हेंबर", 12: "डिसेंबर"}
ENGLISH_MONTHS = {i: m for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def date_en(d):
    return f"{d.day} {ENGLISH_MONTHS[d.month]} {d.year}"


def date_mr(d):
    return f"{d.day} {MARATHI_MONTHS[d.month]} {d.year}"


def market_short(market):
    """Human-friendly market name for verdicts: 'Lasalgaon APMC' -> 'Lasalgaon'."""
    m = market.replace(" APMC", "")
    return m


MARKET_MR = {  # spoken-Marathi locative forms for known Nashik markets
    "Lasalgaon": "लासलगावला", "Lasalgaon(Niphad)": "लासलगाव (निफाड) येथे",
    "Lasalgaon(Vinchur)": "लासलगाव (विंचूर) येथे", "Nasik": "नाशिकला",
    "Pimpalgaon Baswant": "पिंपळगाव बसवंतला", "Devala": "देवळ्याला",
    "Manmad": "मनमाडला", "Yeola": "येवल्याला", "Satana": "सटाण्याला",
    "Kalvan": "कळवणला", "Sinner": "सिन्नरला", "Umrane": "उमराण्याला",
    "Nandgaon": "नांदगावला", "Ghoti": "घोटीला",
}


def market_mr(market):
    return MARKET_MR.get(market_short(market), f"{market_short(market)} येथे")


def pct(cur, base):
    return (cur - base) / base * 100.0


def daily_series(df):
    """market+commodity+date -> median modal (one number per market-commodity-day)."""
    return (df.groupby(["market", "commodity", "arrival_date"], as_index=False)
              .agg(modal=("modal_price", "median"),
                   min_price=("min_price", "min"),
                   max_price=("max_price", "max")))


def analyze_market(series, market):
    """series: daily_series rows for one market, sorted by date."""
    s = series[series["market"] == market].sort_values("arrival_date")
    dates = list(s["arrival_date"])
    cur = s.iloc[-1]
    prior = s.iloc[:-1]
    n_prior = len(prior)
    out = {
        "market": market,
        "date": str(cur["arrival_date"]),
        "modal": round(float(cur["modal"])),
        "min": round(float(cur["min_price"])),
        "max": round(float(cur["max_price"])),
        "trading_days": len(dates),
        "pct_7d": None, "pct_30d": None,
        "status": "BASELINE",
        "baseline_since": str(dates[0]),
    }
    if n_prior >= WINDOW_7:
        avg7 = float(prior.tail(WINDOW_7)["modal"].mean())
        out["pct_7d"] = round(pct(float(cur["modal"]), avg7), 1)
        move = abs(out["pct_7d"])
        out["status"] = ("ALERT" if move > ALERT_PCT
                         else "NOTABLE" if move > NOTABLE_PCT else "STEADY")
        out.pop("baseline_since")
        if n_prior >= WINDOW_30:
            avg30 = float(prior.tail(WINDOW_30)["modal"].mean())
            out["pct_30d"] = round(pct(float(cur["modal"]), avg30), 1)
    return out


def verdicts(h):
    """Bilingual verdict strings for the headline market summary dict."""
    name_en = market_short(h["market"])
    name_mr = market_mr(h["market"])
    price_en = f"₹{h['modal']:,}/quintal"
    price_mr = f"₹{h['modal']:,} प्रति क्विंटल"
    if h["status"] == "BASELINE":
        since = datetime.strptime(h["baseline_since"], "%Y-%m-%d").date()
        en = (f"Onion at {name_en}: {price_en} today. Building the price baseline "
              f"since {date_en(since)} — trend alerts start after 7 market days.")
        mr = (f"{name_mr} आज कांदा {price_mr}. {date_mr(since)} पासून भावाची नोंद "
              f"सुरू आहे — 7 बाजार दिवसांनंतर वाढ-घट दिसू लागेल.")
        return en, mr
    p = h["pct_7d"]
    up = p >= 0
    ap = abs(p)
    if h["status"] == "ALERT":
        en = (f"Onion at {name_en} {'jumped' if up else 'dropped'} {ap:.0f}% vs the "
              f"7-day average — {price_en} today.")
        mr = (f"{name_mr} कांदा {'चांगलाच वधारला' if up else 'बराच उतरला'} — आज {price_mr}, "
              f"7 दिवसांच्या सरासरीपेक्षा {ap:.0f}% {'जास्त' if up else 'कमी'}.")
    elif h["status"] == "NOTABLE":
        en = (f"Onion at {name_en} {'edged up' if up else 'eased'} {ap:.0f}% vs the "
              f"7-day average — {price_en} today.")
        mr = (f"{name_mr} कांदा थोडा {'वधारला' if up else 'उतरला'} — आज {price_mr}, "
              f"7 दिवसांच्या सरासरीपेक्षा {ap:.0f}% {'जास्त' if up else 'कमी'}.")
    else:
        en = f"Onion steady at {name_en}: {price_en}, close to the 7-day average."
        mr = f"{name_mr} कांद्याचा भाव स्थिर — आज {price_mr}, 7 दिवसांच्या सरासरीइतकाच."
    return en, mr


def top_movers(nashik_daily, latest_date, n=5):
    """Day-over-day movers across ALL Nashik commodities (needs >=2 trading days)."""
    movers = []
    for (mkt, com), g in nashik_daily.groupby(["market", "commodity"]):
        g = g.sort_values("arrival_date")
        if len(g) < 2 or str(g.iloc[-1]["arrival_date"]) != latest_date:
            continue
        cur, prev = float(g.iloc[-1]["modal"]), float(g.iloc[-2]["modal"])
        if prev <= 0:
            continue
        movers.append({"market": mkt, "commodity": com,
                       "modal": round(cur), "prev_modal": round(prev),
                       "pct_vs_prev_day": round(pct(cur, prev), 1)})
    movers.sort(key=lambda m: -abs(m["pct_vs_prev_day"]))
    return movers[:n]


def main():
    if not os.path.exists(HISTORY):
        print(f"FATAL: {HISTORY} not found — run fetch_mandi.py first")
        sys.exit(1)
    df = pd.read_csv(HISTORY)
    nashik = df[df["district"] == DISTRICT]
    if nashik.empty:
        print("FATAL: no Nashik rows in history.csv")
        sys.exit(1)

    latest_date = nashik["arrival_date"].max()
    d = datetime.strptime(latest_date, "%Y-%m-%d").date()

    # --- onion per Nashik market ------------------------------------------
    onion_nashik = nashik[nashik["commodity"] == ONION]
    onion_series = daily_series(onion_nashik)
    markets_today = sorted(
        onion_series[onion_series["arrival_date"] == latest_date]["market"].unique())
    summaries = [analyze_market(onion_series, m) for m in markets_today]

    # --- headline yard (contract: prefix match, fixed priority, labeled) ---
    lasalgaon = [s for s in summaries if s["market"].startswith("Lasalgaon")]
    priority = {"Lasalgaon APMC": 0, "Lasalgaon(Niphad) APMC": 1, "Lasalgaon(Vinchur) APMC": 2}
    headline = None
    if lasalgaon:
        headline = sorted(lasalgaon, key=lambda s: priority.get(s["market"], 9))[0]
    elif summaries:
        headline = max(summaries, key=lambda s: s["trading_days"])  # fallback, labeled
    if headline is None:
        print("FATAL: no onion rows for the latest date — nothing to report")
        sys.exit(1)
    verdict_en, verdict_mr = verdicts(headline)

    # --- district comparison: Nashik vs all-Maharashtra onion today --------
    onion_mh = df[(df["commodity"] == ONION) & (df["arrival_date"] == latest_date)]
    mh_comparison = {
        "nashik_median_modal": round(float(
            onion_nashik[onion_nashik["arrival_date"] == latest_date]["modal_price"].median())),
        "maharashtra_median_modal": round(float(onion_mh["modal_price"].median())),
        "maharashtra_markets_reporting": int(onion_mh["market"].nunique()),
    }

    nashik_daily = daily_series(nashik)
    movers = top_movers(nashik_daily, latest_date)

    # --- 3 non-onion commodities for the card table -------------------------
    # Deterministic: staples first if they reported today, biggest movers as
    # tie-break, then whatever else reported. One row per commodity.
    STAPLES = ["Tomato", "Wheat", "Maize", "Bajra(Pearl Millet/Cumbu)",
               "Pomegranate", "Cabbage", "Cauliflower", "Banana", "Grapes"]
    today_rows = nashik_daily[(nashik_daily["arrival_date"] == latest_date)
                              & (nashik_daily["commodity"] != ONION)]
    mover_pct = {(m["market"], m["commodity"]): m["pct_vs_prev_day"] for m in movers}
    key_commodities = []
    seen = set()
    ordered = ([c for c in STAPLES if c in set(today_rows["commodity"])] +
               [c for c in today_rows["commodity"] if c not in STAPLES])
    for com in ordered:
        if com in seen or len(key_commodities) == 3:
            continue
        seen.add(com)
        g = today_rows[today_rows["commodity"] == com]
        r = g.iloc[g["modal"].argmax() if len(g) > 1 else 0]  # busiest quote: highest modal row
        key_commodities.append({
            "commodity": com, "market": r["market"],
            "modal": round(float(r["modal"])),
            "pct_vs_prev_day": mover_pct.get((r["market"], com)),
        })

    out = {
        "date": latest_date,
        "date_display": {"en": date_en(d), "mr": date_mr(d)},
        "generated_at": datetime.now(IST).isoformat(timespec="seconds"),
        "headline": {**headline, "verdict_en": verdict_en, "verdict_mr": verdict_mr},
        "onion_markets": summaries,
        "top_movers": movers,
        "key_commodities": key_commodities,
        "top_movers_note": (None if movers else
                            "fewer than 2 trading days of history — movers start tomorrow"),
        "mh_onion_comparison": mh_comparison,
        "source": "AGMARKNET via data.gov.in",
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"wrote {OUT}")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
