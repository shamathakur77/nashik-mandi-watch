#!/usr/bin/env python3
"""
make_card.py — renders the bilingual 1080x1350 daily card from reports/latest.json.

Design: stat-tile contract (label / hero value / delta vs named period / small
table), light surface + near-black ink for phone-in-sunlight contrast.
Fonts: bundled Noto Sans Devanagari (covers Devanagari + Latin + ₹), shaped by
Pillow's raqm layout so Marathi conjuncts render correctly.
Cold start: BASELINE status renders the bilingual "building baseline" line —
never a fake 0% or an empty arrow.

Output: reports/cards/YYYY-MM-DD.png and reports/latest-card.png
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont, features

W, H = 1080, 1350
M = 64  # outer margin

# palette (dataviz reference instance, light mode)
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
HAIRLINE = "#e1e0d9"
UP = "#006300"     # price up = good for the farmer
DOWN = "#d03b3b"
BASELINE_ACCENT = "#1c5cab"

FONT_DIR = "assets"
REG = os.path.join(FONT_DIR, "NotoSansDevanagari-Regular.ttf")
BOLD = os.path.join(FONT_DIR, "NotoSansDevanagari-Bold.ttf")

COMMODITY_MR = {
    "Onion": "कांदा", "Tomato": "टोमॅटो", "Wheat": "गहू", "Maize": "मका",
    "Bajra(Pearl Millet/Cumbu)": "बाजरी", "Jowar(Sorghum)": "ज्वारी",
    "Pomegranate": "डाळिंब", "Cabbage": "कोबी", "Cauliflower": "फ्लॉवर",
    "Banana": "केळी", "Grapes": "द्राक्षे", "Guava": "पेरू", "Apple": "सफरचंद",
    "Papaya": "पपई", "Tender Coconut": "शहाळे", "Cucumbar(Kheera)": "काकडी",
    "Green Chilli": "हिरवी मिरची", "Rice": "तांदूळ", "Potato": "बटाटा",
    "Garlic": "लसूण", "Soybean": "सोयाबीन",
}


def commodity_en(c):
    return c.split("(")[0].strip()


def font(path, size):
    return ImageFont.truetype(path, size)


def text_w(d, s, f):
    return d.textlength(s, font=f)


def fit_font(d, s, path, size, max_w, min_size=24):
    """Largest font <= size whose rendered width fits max_w. Measure, never clip."""
    while size > min_size and d.textlength(s, font=font(path, size)) > max_w:
        size -= 2
    return font(path, size)


def draw_triangle(d, cx, cy, size, up, color):
    h = size * 0.85
    if up:
        pts = [(cx - size / 2, cy + h / 2), (cx + size / 2, cy + h / 2), (cx, cy - h / 2)]
    else:
        pts = [(cx - size / 2, cy - h / 2), (cx + size / 2, cy - h / 2), (cx, cy + h / 2)]
    d.polygon(pts, fill=color)


def main():
    if not features.check("raqm"):
        print("FATAL: Pillow lacks raqm text shaping — Marathi would render wrong. "
              "Install a Pillow wheel with raqm (pip's manylinux wheels have it).")
        sys.exit(1)
    with open(os.path.join("reports", "latest.json"), encoding="utf-8") as f:
        data = json.load(f)

    h = data["headline"]
    img = Image.new("RGB", (W, H), SURFACE)
    d = ImageDraw.Draw(img)

    f_kicker = font(BOLD, 40)
    f_date = font(REG, 36)
    f_label = font(REG, 42)
    f_hero = font(BOLD, 170)
    f_unit = font(REG, 44)
    f_delta = font(BOLD, 52)
    f_delta_sub = font(REG, 38)
    f_range = font(REG, 36)
    f_tbl = font(REG, 40)
    f_tbl_b = font(BOLD, 40)
    f_foot = font(REG, 30)
    inner_w = W - 2 * M

    y = M
    # header: kicker + bilingual date
    d.text((M, y), "NASHIK MANDI WATCH", font=f_kicker, fill=MUTED)
    date_s = f"{data['date_display']['mr']}  ·  {data['date_display']['en']}"
    d.text((W - M - text_w(d, date_s, f_date), y + 4), date_s, font=f_date, fill=INK2)
    y += 78
    d.line([(M, y), (W - M, y)], fill=HAIRLINE, width=2)
    y += 56

    # hero label: market + commodity, bilingual
    mkt = h["market"].replace(" APMC", "")
    s = f"कांदा — {mkt}"
    d.text((M, y), s, font=fit_font(d, s, BOLD, 64, inner_w), fill=INK)
    y += 84
    s = f"Onion · {h['market']} · modal price"
    d.text((M, y), s, font=fit_font(d, s, REG, 42, inner_w), fill=INK2)
    y += 84

    # hero number
    hero = f"₹{h['modal']:,}"
    d.text((M - 6, y), hero, font=f_hero, fill=INK)
    hero_w = text_w(d, hero, f_hero)
    d.text((M + hero_w + 28, y + 118), "प्रति क्विंटल\nper quintal",
           font=f_unit, fill=INK2, spacing=10)
    y += 232

    # delta row OR baseline line — never an empty arrow
    if h["status"] == "BASELINE":
        box_h = 134
        d.rounded_rectangle([(M, y), (W - M, y + box_h)], radius=16,
                            outline=BASELINE_ACCENT, width=3)
        s = f"{data['date_display']['mr']} पासून नोंद सुरू — तुलना लवकरच."
        d.text((M + 32, y + 20), s,
               font=fit_font(d, s, BOLD, 42, inner_w - 64), fill=BASELINE_ACCENT)
        s = "Building the baseline — trend arrows after 7 market days."
        d.text((M + 32, y + 80), s,
               font=fit_font(d, s, REG, 36, inner_w - 64), fill=INK2)
        y += box_h + 28
    else:
        p = h["pct_7d"]
        up = p >= 0
        col = UP if up else DOWN
        draw_triangle(d, M + 26, y + 34, 44, up, col)
        delta_s = f"{'+' if up else '−'}{abs(p):.0f}%"
        d.text((M + 70, y), delta_s, font=f_delta, fill=col)
        dx = M + 70 + text_w(d, delta_s, f_delta) + 24
        d.text((dx, y + 10), "vs 7-day avg · ७ दिवसांच्या सरासरीशी तुलना",
               font=f_delta_sub, fill=INK2)
        y += 76
        if h.get("pct_30d") is not None:
            p30 = h["pct_30d"]
            d.text((M + 70, y), f"{'+' if p30 >= 0 else '−'}{abs(p30):.0f}% vs 30-day avg",
                   font=f_range, fill=MUTED)
            y += 54
        y += 24

    # today's range
    d.text((M, y), f"आजचा भाव: ₹{h['min']:,} ते ₹{h['max']:,}  ·  today's range",
           font=f_range, fill=MUTED)
    y += 56

    # footer geometry first, so the table can never collide with it
    fy = H - M - 76
    content_floor = fy - 26

    # table: 3 other commodities
    d.line([(M, y), (W - M, y)], fill=HAIRLINE, width=2)
    y += 24
    d.text((M, y), "इतर भाव · other prices (₹/क्विंटल)", font=font(BOLD, 38), fill=INK2)
    y += 58
    row_h = 92
    for row in data.get("key_commodities", [])[:3]:
        if y + row_h > content_floor:
            break  # never overlap the footer; remaining rows live in latest.json
        c_en = commodity_en(row["commodity"])
        c_mr = COMMODITY_MR.get(row["commodity"], "")
        name = f"{c_mr} · {c_en}" if c_mr else c_en
        d.text((M, y), name, font=fit_font(d, name, BOLD, 40, inner_w - 260), fill=INK)
        d.text((M, y + 50), row["market"].replace(" APMC", ""), font=font(REG, 30), fill=MUTED)
        val = f"₹{row['modal']:,}"
        d.text((W - M - text_w(d, val, f_tbl_b), y), val, font=f_tbl_b, fill=INK)
        pct = row.get("pct_vs_prev_day")
        if pct is not None:
            col = UP if pct >= 0 else DOWN
            ps = f"{'+' if pct >= 0 else '−'}{abs(pct):.0f}% कालपेक्षा"
            d.text((W - M - text_w(d, ps, f_range), y + 50), ps, font=f_range, fill=col)
        y += row_h
        d.line([(M, y - 12), (W - M, y - 12)], fill=HAIRLINE, width=1)
    if not data.get("key_commodities"):
        d.text((M, y), "आज इतर भाव उपलब्ध नाहीत · no other quotes today",
               font=f_tbl, fill=MUTED)
        y += 70

    # footer pinned to bottom
    d.line([(M, fy - 24), (W - M, fy - 24)], fill=HAIRLINE, width=2)
    d.text((M, fy), "Source: AGMARKNET via data.gov.in", font=f_foot, fill=MUTED)
    d.text((M, fy + 40), "रोज सकाळी ताजे भाव · github.com/shamathakur77/nashik-mandi-watch",
           font=f_foot, fill=MUTED)

    os.makedirs(os.path.join("reports", "cards"), exist_ok=True)
    day_path = os.path.join("reports", "cards", f"{data['date']}.png")
    img.save(day_path)
    img.save(os.path.join("reports", "latest-card.png"))
    print(f"card saved: {day_path} and reports/latest-card.png")


if __name__ == "__main__":
    main()
