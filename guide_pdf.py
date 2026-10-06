"""Lay out a series guide (Personal or Tribe) as a letter-size PDF.

Every word comes from GrowthTrack's course pack for each message
(gt_el_lessons.pack): the title, the memory verse, the big idea, Pastor
Donte's own words, the discussion questions, the "Living it" steps and the
five-day devotional. This file only arranges them. It writes no copy of its
own beyond section labels, so the booklet can never say something the course
does not.

The look follows the hand-built 2026 guides: Helvetica, a cover band of the
series art, orange labels, a faint message number in the corner.
"""
import io
import re

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

W, H = letter
M = 56
CW = W - 2 * M
BOTTOM = 64
ORANGE = HexColor("#D9541E")
TAN = HexColor("#B98A4B")
INK = HexColor("#1B1B1B")
BODY = HexColor("#2A2A2A")
GREY = HexColor("#6E6E6E")
FAINT = HexColor("#F1E9DF")
CREAM = HexColor("#F8F4EE")
RULE = HexColor("#E3DCD2")

PERSONAL = "Personal Guide"
TRIBE = "Tribe Guide"


def clean(s):
    """Fit text to the core fonts (cp1252) and the house's no-em-dash rule."""
    s = (s or "").replace("—", ", ").replace("–", "-").replace("…", "...")
    s = re.sub(r"\s+,", ",", s)
    return s.encode("cp1252", "replace").decode("cp1252").strip()


def living_it(pack):
    """The points under the lesson's closing "Living it" heading, if it has one."""
    out, inside = [], False
    for b in pack.get("lesson") or []:
        if b.get("kind") == "heading":
            inside = "living" in (b.get("text") or "").lower()
            continue
        if inside and b.get("kind") == "point":
            out.append(b.get("text") or "")
    return out


class Guide:
    def __init__(self, kind, series, messages, cover_bytes=None, running=False):
        """series: {title, sticky, anchor, dates}; messages: dicts with
        week, date_label, service, pack, quote (verified or None)."""
        self.kind = kind
        self.tribe = kind == TRIBE
        self.series = series
        self.messages = messages
        self.cover = cover_bytes
        self.running = running
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=letter)
        self.c.setTitle(clean(f"{series['title']} | {kind} | GodChasers Church"))
        self.c.setAuthor("GodChasers Church")
        self.page = 1
        self.y = H - 62

    # ---------- primitives ----------
    def _text(self, x, y, s, font="Helvetica", size=10, color=BODY):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        self.c.drawString(x, y, clean(s))

    def _lines(self, s, font, size, width):
        return simpleSplit(clean(s), font, size, width)

    def room(self, h):
        if self.y - h < BOTTOM:
            self.next_page()

    def para(self, s, font="Helvetica", size=9.2, lead=None, color=BODY, indent=0, center=False, bar=False, right=0):
        lead = lead or size * 1.55
        x = M + indent
        width = CW - indent - right
        lines = self._lines(s, font, size, width)
        top = self.y + size
        for ln in lines:
            if self.y - lead < BOTTOM:
                if bar:
                    self._bar(top, self.y + lead - 4)
                self.next_page()
                top = self.y + size
            self.c.setFont(font, size)
            self.c.setFillColor(color)
            if center:
                self.c.drawCentredString(x + width / 2, self.y, ln)
            else:
                self.c.drawString(x, self.y, ln)
            self.y -= lead
        if bar:
            self._bar(top, self.y + lead - 4)

    def _bar(self, top, bottom):
        self.c.setStrokeColor(ORANGE)
        self.c.setLineWidth(2)
        self.c.line(M + 1, top, M + 1, bottom)

    def label(self, s, color=GREY, before=10):
        self.y -= before
        self.room(40)
        self.c.setFont("Helvetica-Bold", 7.5)
        self.c.setFillColor(color)
        self.c.drawString(M, self.y, " ".join(clean(s).upper()))
        self.y -= 15

    def footer(self):
        self.c.setStrokeColor(RULE)
        self.c.setLineWidth(0.6)
        self.c.line(M, 44, W - M, 44)
        self._text(M, 32, f"{self.series['title']}  |  {self.kind}  |  GodChasers Church", size=7, color=GREY)
        self.c.setFont("Helvetica", 7)
        self.c.drawRightString(W - M, 32, str(self.page))

    def next_page(self):
        self.footer()
        self.c.showPage()
        self.page += 1
        self.y = H - 62

    # ---------- cover ----------
    def cover_page(self):
        band = W * 1080 / 1920 * 0.86
        if self.cover:
            try:
                img = ImageReader(io.BytesIO(self.cover))
                iw, ih = img.getSize()
                dh = W * ih / iw
                self.c.saveState()
                p = self.c.beginPath()
                p.rect(0, H - band, W, band)
                self.c.clipPath(p, stroke=0, fill=0)
                self.c.drawImage(img, 0, H - band - (dh - band) / 2, W, dh)
                self.c.restoreState()
            except Exception:
                self.cover = None
        if not self.cover:
            self.c.setFillColor(INK)
            self.c.rect(0, H - band, W, band, stroke=0, fill=1)

        s = self.series
        y = H - band - 38
        self.c.setFont("Helvetica-Bold", 7.5)
        self.c.setFillColor(ORANGE)
        self.c.drawString(M, y, "G O D C H A S E R S   C H U R C H      |      " + " ".join(self.kind.upper()))
        y -= 30
        self._text(M, y, s["title"], "Helvetica-Bold", 24, INK)
        y -= 18
        n = len(self.messages)
        count = f"{n} message{'' if n == 1 else 's'}{' so far' if self.running else ''}"
        self._text(M, y, f"{s['dates']}  |  {count}", size=9.5, color=GREY)
        if s.get("sticky"):
            y -= 26
            self._text(M, y, f"\"{s['sticky']}\"", "Helvetica-BoldOblique", 13, ORANGE)
        if s.get("anchor"):
            y -= 18
            self._text(M, y, "ANCHOR", "Helvetica-Bold", 7.5, TAN)
            self._text(M + 40, y, s["anchor"], "Helvetica-Bold", 7.5, TAN)
        y -= 26
        self.c.setFont("Helvetica-Bold", 7.5)
        self.c.setFillColor(ORANGE)
        self.c.drawString(M, y, " ".join("A WORD BEFORE YOU BEGIN"))
        y -= 15
        if self.tribe:
            how = ("How to lead this: one message per gathering. Read the memory verse together, then the big idea. "
                   "Let the questions do the work, take Go Do It seriously, and point people to Go Deeper for the week. "
                   "Your job isn't to have the answers. It's to keep the circle honest and finish on time.")
        else:
            how = ("How to use this guide: one message at a time. Read the memory verse until you can say it, sit with "
                   "the big idea and the questions, then walk through the five days with it. Every page matches the "
                   "lesson in GrowthTrack, so you can read here, watch there, and never lose your place.")
        if self.running:
            how += " This guide grows as the series goes; a fresh copy lands after each new message."
        self.y = y
        self.para(how, "Helvetica-Oblique", 8.8, color=GREY)

        self.c.setFillColor(CREAM)
        self.c.rect(0, 0, W, 78, stroke=0, fill=1)
        self._text(M, 46, "mygc3.church/series  |  grow.godchasers.church", "Helvetica-Bold", 8.5, ORANGE)
        self._text(M, 31, "Watch every message on the Sermon Calendar. Take the full lesson and quiz in GrowthTrack.",
                   size=7.5, color=GREY)
        self.c.showPage()
        self.page += 1
        self.y = H - 62

    # ---------- one message ----------
    def message(self, n, m):
        pack = m["pack"]
        c = self.c
        c.setFont("Helvetica-Bold", 46)
        c.setFillColor(FAINT)
        c.drawRightString(W - M, self.y - 22, f"{n:02d}")

        head = [f"WEEK {m['week']}" if m.get("week") else None, m.get("date_label"), m.get("service")]
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(ORANGE)
        c.drawString(M, self.y, clean("   |   ".join(h for h in head if h)))
        self.y -= 22
        for ln in self._lines(pack.get("title") or "", "Helvetica-Bold", 17, CW - 70):
            self._text(M, self.y, ln, "Helvetica-Bold", 17, INK)
            self.y -= 20
        if pack.get("subtitle"):
            self.y += 4
            self.para(pack["subtitle"], "Helvetica-Oblique", 9, lead=12.5, color=GREY, right=70)

        mv = pack.get("memory_verse") or {}
        if mv.get("text"):
            self.label("Memory verse")
            self.para(f"\"{mv['text']}\"", "Helvetica-Oblique", 9.5, indent=12, color=INK, bar=True)
            self._text(M + 12, self.y + 3, f"- {mv.get('ref', '')}, KJV", "Helvetica-Bold", 7.5, ORANGE)
            self.y -= 10
        also = [pack.get("passage")] + [g.get("ref") for g in (pack.get("go_deeper") or [])[:3]]
        also = [a for a in also if a]
        if also and not self.tribe:
            self.room(14)
            self._text(M, self.y, "Read also: " + " | ".join(also), size=7.5, color=GREY)
            self.y -= 8

        if pack.get("big_idea"):
            self.label("The big idea")
            self.para(pack["big_idea"], "Helvetica-Bold", 9.5, lead=14, color=INK)

        if m.get("quote"):
            self.y -= 8
            self.room(60)
            c.setStrokeColor(ORANGE)
            c.setLineWidth(0.8)
            c.line(W / 2 - 40, self.y + 6, W / 2 + 40, self.y + 6)
            self.y -= 12
            self.para(f"\"{m['quote']}\"", "Helvetica-BoldOblique", 11, lead=15, color=ORANGE, center=True,
                      indent=20)
            c.setStrokeColor(ORANGE)
            c.line(W / 2 - 40, self.y + 8, W / 2 + 40, self.y + 8)
            self.y -= 6

        qs = pack.get("discussion") or []
        if qs:
            self.label("Talk about it" if self.tribe else "Reflect")
            for i, q in enumerate(qs if self.tribe else qs[:3], 1):
                self.room(28)
                self._text(M, self.y, f"{i}.", "Helvetica-Bold", 9, ORANGE)
                self.para(q, size=9, lead=13, indent=16)
                self.y -= 3

        steps = living_it(pack)
        if steps:
            self.label("Go do it" if self.tribe else "Live it this week", TAN)
            for s in steps:
                self.para(s, "Helvetica", 9, lead=13, indent=12, color=INK)
                self.y -= 3

        if self.tribe:
            gd = pack.get("go_deeper") or []
            if gd:
                self.label("Go deeper this week")
                for g in gd:
                    self.para(f"{g.get('ref', '')}: {g.get('why', '')}", size=8.8, lead=12.5, indent=12)
                    self.y -= 2
        else:
            devo = pack.get("devo") or []
            if devo:
                self.label("Five days with it", ORANGE, before=16)
                for d in devo:
                    self.room(90)
                    head = f"DAY {d.get('day', '')}   |   {d.get('title', '')}   |   {d.get('ref', '')}"
                    self._text(M, self.y, head, "Helvetica-Bold", 8.5, INK)
                    self.y -= 15
                    for p in (d.get("body") or "").split("\n\n"):
                        self.para(p, size=8.8, lead=13)
                        self.y -= 3
                    if d.get("action"):
                        self.para("Do this: " + d["action"], "Helvetica-Bold", 8.8, lead=13, indent=12, color=INK)
                    if d.get("prayer"):
                        self.para(d["prayer"], "Helvetica-Oblique", 8.8, lead=13, indent=12, bar=True)
                    self.y -= 10

        self.next_page()

    def build(self):
        self.cover_page()
        for n, m in enumerate(self.messages, 1):
            self.message(n, m)
        self.c.save()
        return self.buf.getvalue()
