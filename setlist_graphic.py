"""Fridays: Sunday's setlist from Planning Center, made into graphics for social.

Reads the songs on the coming week's plans in Planning Center **Services**,
draws three setlist graphics (each as a 4:5 feed post and a 9:16 story) and
emails them to the staff who post them: PD, media@, Latwanna and Tiffany.

This is a STAFF email. It never goes to a member. `send_staff_email()` refuses
any address that is not DIGEST_TO or an @godchasers.church mailbox, so a typo
in a secret cannot turn it into a mailing list. Member email is a Pathway
(gc3-intranet, src/lib/pathways/); see CLAUDE.md before widening anything here.

No songs on the plan yet? It still emails, saying so, with the link to the
plan, so the team knows to chase the worship leader rather than wondering
whether the job ran.

Env:
  PCO_APP_ID, PCO_SECRET   Planning Center personal access token
  RESEND_API_KEY           sending (absent = dry run)
  DIGEST_TO                PD's address (default dontebee@gmail.com)
  SETLIST_EXTRA_TO         more staff, comma separated, @godchasers.church only
                           (the social team's address goes here)
  SETLIST_SERVICE_TYPES    PCO service type ids (default: Central Campus and
                           Special Events)
  SETLIST_DAYS             how far ahead counts as "upcoming" (default 7)
  DRY_RUN=1                draw the PNGs into ./setlist-out, send nothing
"""
import base64
import datetime as dt
import math
import os
import random
import re
import sys
from html import escape
from pathlib import Path

import requests
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"
OUT = HERE / "setlist-out"

PCO_BASE = "https://api.planningcenteronline.com"
PCO_APP_ID = (os.environ.get("PCO_APP_ID") or "").strip()
PCO_SECRET = (os.environ.get("PCO_SECRET") or "").strip()
RESEND_API_KEY = (os.environ.get("RESEND_API_KEY") or "").strip()
DIGEST_TO = (os.environ.get("DIGEST_TO") or "dontebee@gmail.com").strip()
DRY_RUN = bool(os.environ.get("DRY_RUN")) or not RESEND_API_KEY
FROM = "GC3 Setlist <hello@godchasers.church>"
REPLY_TO = "media@godchasers.church"

# 644335 is the Central Campus type that holds the Sunday plans; 1801745 shares
# the name but is empty. 882606 is Special Events.
SERVICE_TYPES = [s.strip() for s in (os.environ.get("SETLIST_SERVICE_TYPES")
                                     or "644335,882606").split(",") if s.strip()]
DAYS = int(os.environ.get("SETLIST_DAYS") or 7)

STAFF_DOMAIN = "@godchasers.church"
STAFF_TO = [
    DIGEST_TO,
    "media@godchasers.church",
    "Latwanna@GodChasers.church",
    "TiffanyA@GodChasers.church",
] + [a.strip() for a in (os.environ.get("SETLIST_EXTRA_TO") or "").split(",") if a.strip()]


# --------------------------------------------------------------------------
# Planning Center
# --------------------------------------------------------------------------

def pco_get(path, params=None):
    """GET with retry on 429/5xx (PCO rate-limits hard)."""
    import time
    for attempt in range(5):
        r = requests.get(PCO_BASE + path, params=params or {},
                         auth=(PCO_APP_ID, PCO_SECRET), timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            wait = int(r.headers.get("Retry-After") or 2 ** attempt)
            print(f"  PCO {r.status_code} on {path}, retrying in {wait}s...")
            time.sleep(min(wait, 30))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def upcoming_plans(now):
    """Plans dated from now through DAYS ahead, across SERVICE_TYPES, soonest first."""
    horizon = now + dt.timedelta(days=DAYS)
    plans = []
    for st in SERVICE_TYPES:
        data = pco_get(f"/services/v2/service_types/{st}/plans",
                       {"filter": "future", "order": "sort_date", "per_page": 25})
        for p in data.get("data", []):
            a = p["attributes"]
            when = dt.datetime.fromisoformat(a["sort_date"].replace("Z", "+00:00"))
            if when > horizon:
                break
            plans.append({
                "id": p["id"], "service_type": st, "when": when,
                "title": (a.get("title") or "").strip(),
                "dates": a.get("dates") or when.strftime("%B %-d, %Y"),
                "url": f"https://services.planningcenteronline.com/plans/{p['id']}",
            })
    plans.sort(key=lambda p: p["when"])
    return plans


def credit_line(author):
    """'A, B, C, and D' -> 'A & B' or 'A, B & more'. Planning Center stores the
    songwriters, not the recording artist, so keep it short; the team can swap
    in the artist by hand if they want to."""
    if not author:
        return ""
    names = [n.strip() for n in re.split(r",\s*(?:and\s+)?|\s+and\s+|\s*&\s*", author) if n.strip()]
    if len(names) <= 2:
        return " & ".join(names)
    return f"{names[0]}, {names[1]} & more"


def plan_songs(plan):
    """Songs on the plan, in order, once each. A plan carrying both services
    (9am and 11:11) lists the same song twice; the setlist shows it once."""
    data = pco_get(f"/services/v2/service_types/{plan['service_type']}/plans/{plan['id']}/items",
                   {"include": "song", "per_page": 100})
    songs_by_id = {s["id"]: s["attributes"] for s in data.get("included", []) if s["type"] == "Song"}
    out, seen = [], set()
    for it in data.get("data", []):
        a = it["attributes"]
        if a.get("item_type") != "song":
            continue
        rel = ((it.get("relationships") or {}).get("song") or {}).get("data") or {}
        key = rel.get("id") or a.get("title", "").lower()
        if key in seen:
            continue
        seen.add(key)
        song = songs_by_id.get(rel.get("id"), {})
        title = (a.get("title") or song.get("title") or "").strip()
        feat = ""
        m = re.search(r"\s*\((?:feat\.?|ft\.?|featuring)\s+([^)]+)\)\s*$", title, re.I)
        if m:
            feat, title = m.group(1).strip(), title[:m.start()].strip()
        credit = credit_line(song.get("author"))
        if feat:
            credit = f"feat. {feat}" + (f"  /  {credit}" if credit else "")
        out.append({"title": title, "credit": credit})
    return out


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


ANTON = "Anton-Regular.ttf"
BEBAS = "BebasNeue-Regular.ttf"
ARCHIVO = "ArchivoBlack-Regular.ttf"
SERIF_I = "DMSerifDisplay-Italic.ttf"


def text_w(draw, text, f, spacing=0):
    if not text:
        return 0
    w = draw.textlength(text, font=f)
    return w + spacing * (len(text) - 1)


def draw_spaced(draw, xy, text, f, fill, spacing=0, anchor="la"):
    """Text with tracking. anchor's first letter is l/m/r for the whole run.
    Glyphs are placed on a shared line ('a' ascender or 's' baseline), never
    't', which would lift commas and hyphens to the top of the line."""
    x, y = xy
    vert = {"t": "a"}.get(anchor[1], anchor[1])
    total = text_w(draw, text, f, spacing)
    if anchor[0] == "m":
        x -= total / 2
    elif anchor[0] == "r":
        x -= total
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill, anchor="l" + vert)
        x += draw.textlength(ch, font=f) + spacing


def wrap_to(draw, text, fname, size, max_w, max_lines=2, min_size=28):
    """Largest size <= size at which text fits max_w in at most max_lines."""
    words = text.split()
    while size >= min_size:
        f = font(fname, size)
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if draw.textlength(trial, font=f) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        if len(lines) <= max_lines and all(draw.textlength(l, font=f) <= max_w for l in lines):
            return f, lines
        size -= 2
    f = font(fname, min_size)
    return f, [text]


def fit_one_line(draw, text, fname, size, max_w, spacing_ratio=0.0, min_size=14):
    while size > min_size:
        f = font(fname, size)
        if text_w(draw, text, f, size * spacing_ratio) <= max_w:
            return f
        size -= 1
    return font(fname, min_size)


def grain(img, amount=18, seed=7):
    """Film grain, so flat gradients do not band and look like a template."""
    rnd = random.Random(seed)
    w, h = img.size
    small = Image.new("L", (w // 2, h // 2))
    small.putdata([rnd.randint(128 - amount, 128 + amount) for _ in range((w // 2) * (h // 2))])
    noise = small.resize((w, h), Image.BILINEAR).convert("RGB")
    return ImageChops.overlay(img.convert("RGB"), noise)


def blob(size, xy, r, color, blur):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = xy
    d.ellipse((x - r, y - r, x + r, y + r), fill=color)
    return layer.filter(ImageFilter.GaussianBlur(blur))


def vertical_gradient(size, top, bottom):
    w, h = size
    g = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        g.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return g.resize(size)


def song_block_metrics(n, avail_h, base_title, base_credit):
    """Scale the song list so 1 song looks bold and 8 songs still fit."""
    per = avail_h / max(n, 1)
    title = min(base_title, int(per * 0.52))
    credit = min(base_credit, max(22, int(title * 0.36)))
    return title, credit


def short_date(plan):
    return plan["when"].strftime("%-m.%-d.%y")


def long_date(plan):
    return plan["when"].strftime("%B %-d").upper()


def kicker(plan):
    """'SUNDAY SETLIST' on a Sunday plan; 'TUESDAY SETLIST' otherwise."""
    return plan["when"].strftime("%A").upper()


# --- Style 1: Glow (warm gradient, rings, big white type) -----------------

def style_glow(plan, songs, size):
    W, H = size
    img = vertical_gradient(size, (247, 160, 72), (62, 92, 230)).convert("RGBA")
    for xy, r, c, b in [((W * 0.05, H * 0.30), W * 0.42, (255, 92, 138, 200), 140),
                        ((W * 0.95, H * 0.12), W * 0.35, (255, 196, 92, 210), 120),
                        ((W * 0.85, H * 0.78), W * 0.45, (98, 70, 255, 190), 160),
                        ((W * 0.15, H * 0.95), W * 0.40, (60, 140, 255, 200), 150)]:
        img = Image.alpha_composite(img, blob(size, xy, int(r), c, b))
    rings = Image.new("RGBA", size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(rings)
    for cx, cy, r in [(W * -0.05, H * 0.42, W * 0.36), (W * 1.02, H * 0.60, W * 0.30),
                      (W * 0.50, H * 1.12, W * 0.62)]:
        rd.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, 60), width=int(W * 0.09))
    img = Image.alpha_composite(img, rings.filter(ImageFilter.GaussianBlur(6)))
    img = grain(img, 14).convert("RGBA")

    d = ImageDraw.Draw(img)
    white = (255, 255, 255)
    margin = int(W * 0.08)

    # Date in the corners, like a ticket stub.
    fd = font(SERIF_I, int(W * 0.034))
    d.text((W / 2, int(H * 0.035)), short_date(plan), font=fd, fill=white, anchor="mt")
    d.text((W / 2, H - int(H * 0.035)), short_date(plan), font=fd, fill=white, anchor="mb")
    side = Image.new("RGBA", (int(W * 0.3), int(W * 0.06)), (0, 0, 0, 0))
    ImageDraw.Draw(side).text((side.width / 2, side.height / 2), short_date(plan), font=fd,
                              fill=white, anchor="mm")
    img.alpha_composite(side.rotate(90, expand=True), (int(W * 0.01), int(H * 0.40)))
    img.alpha_composite(side.rotate(-90, expand=True), (W - int(W * 0.07), int(H * 0.55)))

    top = int(H * (0.10 if H > W * 1.5 else 0.08))
    title_size = int(W * 0.2)
    for i, word in enumerate([kicker(plan), "SETLIST"]):
        f = fit_one_line(d, word, ANTON, title_size, W - 2 * margin)
        d.text((W / 2, top), word, font=f, fill=white, anchor="mt")
        top += int(f.size * 1.08)

    list_top = top + int(H * 0.04)
    list_bottom = H - int(H * 0.10)
    t_size, c_size = song_block_metrics(len(songs), list_bottom - list_top, int(W * 0.088), int(W * 0.034))
    y = list_top
    gap = int(t_size * 0.42)
    for s in songs:
        ft, lines = wrap_to(d, s["title"].upper(), ANTON, t_size, W - 2 * margin, 2, 34)
        for ln in lines:
            d.text((W / 2, y), ln, font=ft, fill=white, anchor="mt")
            y += int(ft.size * 1.04)
        if s["credit"]:
            fc = fit_one_line(d, s["credit"], ARCHIVO, int(c_size * 0.82), W - 2 * margin)
            d.text((W / 2, y + 2), s["credit"], font=fc, fill=(255, 255, 255, 230), anchor="mt")
            y += int(fc.size * 1.3)
        y += gap
    return img.convert("RGB")


# --- Style 2: Stage (dark, stage light, gold card, vertical outline title) -

def outline_text_image(text, fname, size, stroke, color):
    f = font(fname, size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, t, r, b = probe.textbbox((0, 0), text, font=f, stroke_width=stroke)
    im = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - l, 2 - t), text, font=f, fill=(0, 0, 0, 0),
                            stroke_width=stroke, stroke_fill=color)
    return im


def style_stage(plan, songs, size):
    W, H = size
    img = Image.new("RGBA", size, (16, 16, 18, 255))
    img = Image.alpha_composite(img, blob(size, (W * 0.18, H * 0.05), int(W * 0.55), (210, 210, 220, 120), 170))
    img = Image.alpha_composite(img, blob(size, (W * 0.10, H * 0.98), int(W * 0.30), (255, 255, 255, 70), 120))
    # Light beams from the top-left rig.
    beams = Image.new("RGBA", size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(beams)
    for ang, a in [(58, 26), (68, 18), (76, 12)]:
        rad = math.radians(ang)
        x2, y2 = W * 0.05 + math.cos(rad) * H * 1.5, math.sin(rad) * H * 1.5
        bd.polygon([(W * 0.05, 0), (x2 - W * 0.10, y2), (x2 + W * 0.10, y2)], fill=(255, 255, 255, a))
    img = Image.alpha_composite(img, beams.filter(ImageFilter.GaussianBlur(40)))
    img = grain(img, 22, seed=11).convert("RGBA")
    d = ImageDraw.Draw(img)

    gold = (216, 198, 106)
    ink = (22, 22, 22)
    # Vertical outlined title down the right edge.
    title = outline_text_image(f"{kicker(plan)} SETLIST", ANTON, int(W * 0.15), max(3, W // 360), (255, 255, 255, 235))
    title = title.rotate(-90, expand=True)
    scale = min(1.0, (H * 0.86) / title.height)
    if scale < 1.0:
        title = title.resize((int(title.width * scale), int(title.height * scale)), Image.LANCZOS)
    tx = W - title.width - int(W * 0.04)
    img.alpha_composite(title, (tx, (H - title.height) // 2))

    # Gold card with an offset hairline frame.
    card_l, card_r = int(W * 0.10), tx - int(W * 0.03)
    card_t, card_b = int(H * 0.24), int(H * 0.80)
    d.rectangle((card_l, card_t, card_r, card_b), fill=gold)
    off = int(W * 0.035)
    d.rectangle((card_l - off, card_t - off, card_r - off * 0.4, card_b + off * 0.6),
                outline=(255, 255, 255, 220), width=max(2, W // 540))

    # Date above the card.
    fdate = font(BEBAS, int(W * 0.07))
    draw_spaced(d, (card_l - off, card_t - off - int(W * 0.03)), long_date(plan), fdate,
                gold, spacing=4, anchor="ls")
    fsmall = font(BEBAS, int(W * 0.032))
    draw_spaced(d, (card_l - off, card_b + off + int(W * 0.07)), "GODCHASERS CHURCH", fsmall,
                (235, 235, 235), spacing=6, anchor="ls")

    pad = int(W * 0.06)
    inner_w = card_r - card_l - 2 * pad
    t_size, c_size = song_block_metrics(len(songs), card_b - card_t - 2 * pad, int(W * 0.075), int(W * 0.03))
    # Measure, then centre the list vertically in the card.
    rows = []
    for s in songs:
        ft, lines = wrap_to(d, s["title"].upper(), ANTON, t_size, inner_w, 2, 30)
        fc = fit_one_line(d, s["credit"].upper(), BEBAS, c_size, inner_w, 0.08) if s["credit"] else None
        h = len(lines) * int(ft.size * 1.05) + (int(fc.size * 1.15) if fc else 0)
        rows.append((ft, lines, fc, s["credit"].upper(), h))
    gap = int(t_size * 0.45)
    total = sum(r[-1] for r in rows) + gap * (len(rows) - 1)
    y = card_t + (card_b - card_t - total) / 2
    for ft, lines, fc, credit, h in rows:
        for ln in lines:
            d.text((card_r - pad, y), ln, font=ft, fill=ink, anchor="rt")
            y += int(ft.size * 1.05)
        if fc:
            draw_spaced(d, (card_r - pad, y), credit, fc, (60, 56, 40), fc.size * 0.08, anchor="rt")
            y += int(fc.size * 1.15)
        y += gap
    return img.convert("RGB")


# --- Style 3: Mist (soft grey, wavy outline title, quiet list) -------------

def wave(img, amp, period, phase=0.0):
    """Ripple an image vertically, column by column, like heat over a stage."""
    w, h = img.size
    out = Image.new("RGBA", (w, h + 2 * amp), (0, 0, 0, 0))
    for x in range(w):
        dy = int(amp + amp * math.sin(2 * math.pi * x / period + phase))
        out.paste(img.crop((x, 0, x + 1, h)), (x, dy))
    return out


def style_mist(plan, songs, size):
    W, H = size
    img = vertical_gradient(size, (238, 238, 238), (196, 196, 198)).convert("RGBA")
    for xy, r, c, b in [((W * 0.70, H * 0.30), W * 0.45, (255, 255, 255, 230), 130),
                        ((W * 0.20, H * 0.75), W * 0.40, (170, 170, 175, 160), 150),
                        ((W * 0.90, H * 0.95), W * 0.35, (255, 255, 255, 200), 120)]:
        img = Image.alpha_composite(img, blob(size, xy, int(r), c, b))
    img = grain(img, 10, seed=3).convert("RGBA")
    d = ImageDraw.Draw(img)
    ink = (30, 30, 30)

    margin = int(W * 0.08)
    y = int(H * 0.07)
    for word in [kicker(plan), "SETLIST"]:
        f = fit_one_line(d, word, ANTON, int(W * 0.27), W - 2 * margin)
        t = outline_text_image(word, ANTON, f.size, max(2, W // 400), ink + (255,))
        t = t.resize((W - 2 * margin, int(t.height * 1.15)), Image.LANCZOS)
        t = wave(t, int(W * 0.022), W * 0.55, phase=0.6 if word == "SETLIST" else 0)
        img.alpha_composite(t, (margin, y))
        y += int(t.height * 0.86)

    right = W - margin
    list_bottom = H - int(H * 0.08)
    list_top = max(y + int(H * 0.05), int(H * 0.52))
    t_size, c_size = song_block_metrics(len(songs), list_bottom - list_top, int(W * 0.048), int(W * 0.026))
    rows = []
    for s in songs:
        ft, lines = wrap_to(d, s["title"], ARCHIVO, t_size, W * 0.62, 2, 24)
        fc = fit_one_line(d, s["credit"], BEBAS, c_size, W * 0.62, 0.06) if s["credit"] else None
        rows.append((ft, lines, fc, s["credit"]))
    gap = int(t_size * 0.75)
    total = sum(len(l) * int(ft.size * 1.15) + (int(fc.size * 1.1) if fc else 0)
                for ft, l, fc, _ in rows) + gap * (len(rows) - 1)
    yy = list_bottom - total
    left = right - int(W * 0.62)
    for ft, lines, fc, credit in rows:
        for ln in lines:
            d.text((left, yy), ln, font=ft, fill=ink, anchor="lt")
            yy += int(ft.size * 1.15)
        if fc:
            draw_spaced(d, (left, yy), credit.upper(), fc, (95, 95, 98), fc.size * 0.06, anchor="lt")
            yy += int(fc.size * 1.1)
        yy += gap
    fd = font(SERIF_I, int(W * 0.04))
    d.text((margin, list_bottom), plan["when"].strftime("%B %-d"), font=fd, fill=ink, anchor="ls")
    return img.convert("RGB")


STYLES = [("glow", style_glow), ("stage", style_stage), ("mist", style_mist)]
SIZES = [("post", (1080, 1350)), ("story", (1080, 1920))]


def render_all(plan, songs):
    """Every style in both sizes. The week's lead style rotates so the feed
    does not repeat itself; the other two ride along as alternates."""
    lead = plan["when"].isocalendar()[1] % len(STYLES)
    ordered = STYLES[lead:] + STYLES[:lead]
    files = []
    stamp = plan["when"].strftime("%Y-%m-%d")
    for name, fn in ordered:
        for label, size in SIZES:
            img = fn(plan, songs, size)
            path = OUT / f"setlist-{stamp}-{name}-{label}.png"
            img.save(path, optimize=True)
            files.append(path)
            print(f"  drew {path.name}")
    return files


# --------------------------------------------------------------------------
# Email (staff only)
# --------------------------------------------------------------------------

def staff_only(addresses):
    """DIGEST_TO and @godchasers.church mailboxes. Anything else is refused,
    by name, in the log. This email is for the people who post the graphic."""
    ok, seen = [], set()
    for a in addresses:
        low = a.lower()
        if low in seen:
            continue
        seen.add(low)
        if low == DIGEST_TO.lower() or low.endswith(STAFF_DOMAIN):
            ok.append(a)
        else:
            print(f"  REFUSED: {a}. The setlist goes to staff only.")
    return ok


def send_staff_email(to, subject, html, files):
    to = staff_only(to)
    if not to:
        print("  nobody to send to")
        return False
    if DRY_RUN:
        print(f"  DRY RUN -> {', '.join(to)}: {subject} ({len(files)} attachments)")
        (OUT / "email.html").write_text(html, encoding="utf-8")
        return True
    attachments = []
    for i, p in enumerate(files):
        att = {"filename": p.name, "content": base64.b64encode(p.read_bytes()).decode()}
        if i == 0:
            att["content_id"] = "lead"  # shown inline in the body
        attachments.append(att)
    r = requests.post("https://api.resend.com/emails",
                      headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                      json={"from": FROM, "to": to, "reply_to": REPLY_TO,
                            "subject": subject, "html": html, "attachments": attachments},
                      timeout=60)
    if r.status_code in (200, 201):
        print(f"  SENT -> {', '.join(to)}: {subject}")
        return True
    print(f"  FAILED ({r.status_code}): {r.text[:300]}")
    return False


def email_html(sections):
    body = []
    for plan, songs, files in sections:
        head = f"{escape(plan['title'] or 'Service')}, {escape(plan['dates'])}"
        if not songs:
            body.append(
                f'<h2 style="margin:24px 0 4px;font-size:18px;">{head}</h2>'
                f'<p style="color:#a33;">No songs on the plan yet, so no graphic this week. '
                f'Once the worship leader adds them, re-run the job from GitHub Actions '
                f'(Setlist graphic, Run workflow, untick dry run).</p>'
                f'<p><a href="{plan["url"]}">Open the plan in Planning Center</a></p>')
            continue
        items = "".join(
            f'<li><b>{escape(s["title"])}</b>'
            + (f'<br><span style="color:#777;font-size:13px;">{escape(s["credit"])}</span>' if s["credit"] else "")
            + "</li>" for s in songs)
        caption = (f"{kicker(plan).title()} setlist \U0001F3B6\n"
                   + "\n".join(f"{s['title']}" for s in songs)
                   + "\n\n#sundaysetlist #godchasers")
        body.append(
            f'<h2 style="margin:24px 0 4px;font-size:18px;">{head}</h2>'
            f'<ol style="padding-left:20px;line-height:1.5;">{items}</ol>'
            f'<p style="margin:12px 0 4px;font-size:13px;color:#555;">Caption to copy:</p>'
            f'<pre style="background:#f4f4f4;padding:12px;border-radius:6px;white-space:pre-wrap;'
            f'font-family:inherit;">{escape(caption)}</pre>'
            f'<p style="font-size:13px;color:#555;">Attached: {len(files)} graphics, three looks, '
            f'each as a feed post (4:5) and a story (9:16). '
            f'<a href="{plan["url"]}">Plan in Planning Center</a></p>')
    lead = ""
    if any(f for _, _, f in sections):
        lead = ('<p><img src="cid:lead" alt="This week\'s setlist graphic" width="360" '
                'style="max-width:100%;border-radius:8px;"></p>')
    return ('<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:560px;color:#111;">'
            '<p>This week\'s setlist, ready to post.</p>' + lead + "".join(body) +
            '<p style="margin-top:28px;font-size:12px;color:#999;">Pulled from Planning Center Services '
            'every Friday. Song credits are the songwriters PCO has on file; swap in the artist if '
            'you prefer.</p></div>')


def main():
    if not (PCO_APP_ID and PCO_SECRET):
        print("ERROR: PCO_APP_ID / PCO_SECRET are not set.")
        sys.exit(1)
    OUT.mkdir(exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    plans = upcoming_plans(now)
    print(f"{len(plans)} plan(s) in the next {DAYS} days")
    sections = []
    for plan in plans:
        songs = plan_songs(plan)
        print(f"- {plan['title'] or 'plan'} {plan['dates']}: {len(songs)} song(s)")
        # Only weekend services get a graphic unless the plan has songs:
        # a midweek prayer meeting with no songs is not news.
        if not songs and plan["when"].weekday() != 6:
            continue
        files = render_all(plan, songs) if songs else []
        sections.append((plan, songs, files))
    if not sections:
        print("No upcoming services; nothing to send.")
        return
    files = [f for _, _, fs in sections for f in fs]
    first = sections[0][0]
    has_songs = any(s for _, s, _ in sections)
    subject = (f"Setlist graphic: {first['dates']}" if has_songs
               else f"No setlist yet for {first['dates']}")
    send_staff_email(STAFF_TO, subject, email_html(sections), files)


if __name__ == "__main__":
    main()
