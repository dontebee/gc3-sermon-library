"""
Stage 1 mechanical extraction, factored out from the Supabase plumbing so it
can be unit-tested and run against local text with no network at all.

The GC3 Exemplar Reading Pass spec is explicit: Stage 1 is extraction, not
judgment. "Extract only what is observable." Some of what it asks for —
scripture references, repeated lines, sentences ending in "?" — really is
just a pattern either matching or not. Some of it — which sentence IS the
governing claim, which point IS where tension resolves — is not observable
in that sense; identifying "the thesis" of a paragraph is itself a reading,
however small. Where the spec asks for something that is really a judgment,
this module surfaces a CANDIDATE from a surface marker (a thesis-signaling
phrase, a contrast connective, a resolution phrase) and says so with a
`confidence` field, rather than quietly asserting the candidate is correct.

Everything here reads left to right, once, over plain text. Nothing here
scores anything or decides whether a sermon is good. That is Stage 2 — PD and
Claude reading 20 sermons closely — and it stays a human judgment even then.

See docs/sermon-reading-pass.md for what each field means and where the
mechanical extraction is known to be weak.
"""
import re

EXTRACTOR_VERSION = "reading-pass-1.0.0"

# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

# Transcripts are spoken text with light punctuation, not prose with
# abbreviations to dodge. A period/question/exclamation followed by
# whitespace and a capital (or end of string) is sentence enough.
_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z"‘“]|$)')


def split_sentences(body):
    """[(offset, text), ...] for each sentence, offsets into `body`."""
    sentences = []
    pos = 0
    for piece in _SENT_SPLIT.split(body):
        piece = piece.strip()
        if not piece:
            continue
        # Recover the real offset: find this piece starting at-or-after pos.
        idx = body.find(piece, pos)
        if idx == -1:
            idx = pos
        sentences.append((idx, piece))
        pos = idx + len(piece)
    return sentences


def pct(offset, char_len):
    if char_len <= 0:
        return 0.0
    return round(100.0 * offset / char_len, 1)


def decile(offset, char_len):
    if char_len <= 0:
        return 0
    return min(9, int(10 * offset / char_len))


def _norm_line(s):
    """Normalize a sentence for repetition matching: casefold, collapse
    whitespace, drop trailing punctuation. Two sentences that differ only in
    a trailing "!" vs "." are the same line spoken twice."""
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[.!?,;:]+$", "", s)
    return s


# ---------------------------------------------------------------------------
# Scripture references — the genuinely mechanical field
# ---------------------------------------------------------------------------

_BOOKS = [
    "genesis", "exodus", "leviticus", "numbers", "deuteronomy", "joshua",
    "judges", "ruth", "samuel", "kings", "chronicles", "ezra", "nehemiah",
    "esther", "job", "psalm", "psalms", "proverbs", "ecclesiastes",
    "song of solomon", "song of songs", "isaiah", "jeremiah", "lamentations",
    "ezekiel", "daniel", "hosea", "joel", "amos", "obadiah", "jonah", "micah",
    "nahum", "habakkuk", "zephaniah", "haggai", "zechariah", "malachi",
    "matthew", "mark", "luke", "john", "acts", "romans", "corinthians",
    "galatians", "ephesians", "philippians", "colossians", "thessalonians",
    "timothy", "titus", "philemon", "hebrews", "james", "peter", "jude",
    "revelation", "revelations",
]
# 1/2/3 Samuel, Kings, Chronicles, Corinthians, Thessalonians, Timothy,
# Peter, John — an optional leading ordinal.
_BOOK_PATTERN = r"(?:[1-3]\s?)?(?:" + "|".join(sorted(_BOOKS, key=len, reverse=True)) + r")"
SCRIPTURE_RE = re.compile(
    r"\b(" + _BOOK_PATTERN + r")\.?\s+(\d{1,3})(?::(\d{1,3})(?:[-–](\d{1,3}))?)?\b",
    re.IGNORECASE,
)


def find_scripture_refs(body, sentences, char_len):
    """[{ref, offset, pct, surrounding_claim}, ...]

    surrounding_claim is the sentence the reference falls inside (or the
    nearest one), quoted verbatim — not a judgment about what the sermon
    claims the verse says, just "here is the sentence this citation sat in."
    """
    refs = []
    for m in SCRIPTURE_RE.finditer(body):
        offset = m.start()
        ref = re.sub(r"\s+", " ", m.group(0)).strip()
        sentence = _sentence_at(sentences, offset, body)
        refs.append({
            "ref": ref,
            "offset": offset,
            "pct": pct(offset, char_len),
            "surrounding_claim": sentence,
        })
    return refs


def _sentence_at(sentences, offset, body):
    """The sentence text containing `offset`, or a fallback slice."""
    for i, (start, text) in enumerate(sentences):
        end = sentences[i + 1][0] if i + 1 < len(sentences) else len(body)
        if start <= offset < end:
            return text
    return body[max(0, offset - 40):offset + 60].strip()


# ---------------------------------------------------------------------------
# Governing claim & tension — marker-based candidates, confidence flagged
# ---------------------------------------------------------------------------

_CLAIM_MARKERS = [
    r"here'?s what i want you to (?:see|know|hear|understand)",
    r"i want you to (?:see|know|hear|understand|get)",
    r"the (?:truth|point|thing) is",
    r"what (?:this|that) (?:text|passage|story) is teaching us",
    r"what i'?m trying to (?:say|tell you)",
    r"if you (?:don'?t )?(?:hear|get|remember) (?:nothing|anything) else",
    r"the big idea",
]
_CLAIM_RE = re.compile("|".join(_CLAIM_MARKERS), re.IGNORECASE)

_TENSION_MARKERS = [
    r"\bbut\b", r"\byet\b", r"\bhowever\b", r"the problem is",
    r"here'?s the thing", r"what if", r"the trouble (?:is|with)",
    r"\bsometimes\b", r"not everything", r"it'?s not that simple",
]
_TENSION_RE = re.compile("|".join(_TENSION_MARKERS), re.IGNORECASE)


def find_governing_claim(sentences, body, char_len):
    if not sentences:
        return {}
    marked = [(o, t) for o, t in sentences if _CLAIM_RE.search(t)]
    if marked:
        offset, verbatim = marked[0]
        confidence = "marker"
        candidates = marked
    else:
        offset, verbatim = sentences[0]
        confidence = "fallback_first_sentence"
        candidates = [sentences[0]]

    restated = _find_restatements(verbatim, sentences, exclude_offset=offset)
    return {
        "first_offset": offset,
        "first_pct": pct(offset, char_len),
        "verbatim": verbatim,
        "confidence": confidence,
        "restated_count": len(restated),
        "restated_offsets": restated,
    }


def find_tension(sentences, char_len):
    if not sentences:
        return {}
    marked = [(o, t) for o, t in sentences if _TENSION_RE.search(t)]
    if not marked:
        return {"first_offset": None, "first_pct": None, "verbatim": None,
                "confidence": "none_found", "recurs_count": 0, "recurs_offsets": []}
    offset, verbatim = marked[0]
    recurs = [o for o, _ in marked[1:]]
    return {
        "first_offset": offset,
        "first_pct": pct(offset, char_len),
        "verbatim": verbatim,
        "confidence": "marker",
        "recurs_count": len(recurs),
        "recurs_offsets": recurs,
    }


def _find_restatements(verbatim, sentences, exclude_offset, min_shared_words=4):
    """Offsets of other sentences sharing a run of significant words with
    `verbatim` — a cheap paraphrase detector. Stopwords excluded so it isn't
    just matching "the" and "and"."""
    stop = {"the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
            "to", "of", "in", "on", "that", "this", "it", "i", "you", "we",
            "he", "she", "they", "for", "with", "as", "be", "not", "so"}
    base = {w for w in re.findall(r"[a-z']+", verbatim.lower()) if w not in stop}
    if len(base) < min_shared_words:
        return []
    hits = []
    for offset, text in sentences:
        if offset == exclude_offset:
            continue
        words = {w for w in re.findall(r"[a-z']+", text.lower()) if w not in stop}
        if len(base & words) >= min_shared_words:
            hits.append(offset)
    return hits


# ---------------------------------------------------------------------------
# Target questions — mechanical: every interrogative sentence
# ---------------------------------------------------------------------------

def find_target_questions(sentences, char_len):
    out = []
    for offset, text in sentences:
        if text.rstrip().endswith("?"):
            out.append({"offset": offset, "pct": pct(offset, char_len), "verbatim": text})
    return out


# ---------------------------------------------------------------------------
# Relief points — candidates only; source_type is a heuristic guess
# ---------------------------------------------------------------------------

_RELIEF_MARKERS = re.compile(
    r"\bbut god\b|\band that'?s when\b|here'?s the good news|"
    r"\bso here'?s\b|\bthat'?s why\b|and just like that|\bbut then\b",
    re.IGNORECASE,
)
_STORY_MARKERS = re.compile(
    r"\bi remember (?:when|the day|a time)\b|let me tell you about|"
    r"\byears ago\b|\bwhen i was\b|true story",
    re.IGNORECASE,
)
_SLOGAN_MARKERS = re.compile(r'["‘“].{3,60}["’”]')


def find_relief_points(sentences, char_len, scripture_offsets):
    scripture_set = set(scripture_offsets)
    out = []
    for offset, text in sentences:
        if not _RELIEF_MARKERS.search(text):
            continue
        near_scripture = any(abs(offset - s) < 300 for s in scripture_set)
        if near_scripture:
            source_type, source_quote = "scripture", text
        elif _STORY_MARKERS.search(text):
            source_type, source_quote = "story", text
        elif _SLOGAN_MARKERS.search(text):
            source_type, source_quote = "slogan", _SLOGAN_MARKERS.search(text).group(0)
        else:
            source_type, source_quote = "assertion", text
        out.append({
            "offset": offset, "pct": pct(offset, char_len), "verbatim": text,
            "source_type": source_type, "source_quote": source_quote,
        })
    return out


# ---------------------------------------------------------------------------
# Repeated lines — mechanical
# ---------------------------------------------------------------------------

def find_repeated_lines(sentences, min_count=3):
    seen = {}
    for offset, text in sentences:
        key = _norm_line(text)
        if len(key) < 8:  # too short to be meaningful ("amen.", "okay.")
            continue
        seen.setdefault(key, {"line": text, "offsets": []})
        seen[key]["offsets"].append(offset)
    return [
        {"line": v["line"], "count": len(v["offsets"]), "offsets": v["offsets"]}
        for v in seen.values() if len(v["offsets"]) >= min_count
    ]


# ---------------------------------------------------------------------------
# Devices: alliteration, anaphora, epistrophe, echo, contrast, simile
# ---------------------------------------------------------------------------

_CONTRAST_RE = re.compile(
    r"\bnot\b.{1,40}\bbut\b|\bthough\b.{1,60}\byet\b|\binstead of\b", re.IGNORECASE
)
_SIMILE_RE = re.compile(r"\b(?:like|as) (?:a|an|the)\b", re.IGNORECASE)


def find_devices(sentences, char_len, claim_anchors):
    """claim_anchors: sorted [(offset, verbatim), ...] from governing_claim +
    tension, used as the "nearest preceding Truth or claim" proxy."""
    devices = []

    def nearest_claim(offset):
        prior = [a for a in claim_anchors if a[0] is not None and a[0] <= offset]
        if not prior:
            return None, None
        a = max(prior, key=lambda a: a[0])
        return a

    for offset, text in sentences:
        words = re.findall(r"[A-Za-z']+", text)

        # Alliteration: 3+ consecutive words sharing a first letter.
        run = 1
        for i in range(1, len(words)):
            if words[i][:1].lower() == words[i - 1][:1].lower() and words[i][:1].isalpha():
                run += 1
                if run == 3:
                    claim_off, claim_txt = nearest_claim(offset)
                    devices.append({"type": "alliteration", "offset": offset,
                                     "pct": pct(offset, char_len), "verbatim": text,
                                     "nearest_claim_offset": claim_off,
                                     "nearest_claim_verbatim": claim_txt})
            else:
                run = 1

        if _CONTRAST_RE.search(text):
            claim_off, claim_txt = nearest_claim(offset)
            devices.append({"type": "contrast", "offset": offset,
                             "pct": pct(offset, char_len), "verbatim": text,
                             "nearest_claim_offset": claim_off,
                             "nearest_claim_verbatim": claim_txt})

        if _SIMILE_RE.search(text):
            claim_off, claim_txt = nearest_claim(offset)
            devices.append({"type": "simile", "offset": offset,
                             "pct": pct(offset, char_len), "verbatim": text,
                             "nearest_claim_offset": claim_off,
                             "nearest_claim_verbatim": claim_txt})

    # Anaphora / epistrophe: 3+ sentences (within a 15-sentence window)
    # sharing the same opening or closing 3+ word phrase.
    def phrase(words, n, from_end=False):
        ws = words[-n:] if from_end else words[:n]
        return " ".join(w.lower() for w in ws) if len(ws) == n else None

    tokenized = [(o, t, re.findall(r"[A-Za-z']+", t)) for o, t in sentences]
    for n in (3, 2):
        for label, from_end in (("anaphora", False), ("epistrophe", True)):
            seen = {}
            for offset, text, words in tokenized:
                p = phrase(words, n, from_end)
                if not p:
                    continue
                seen.setdefault(p, []).append((offset, text))
            for p, hits in seen.items():
                if len(hits) >= 3:
                    offset, text = hits[0]
                    claim_off, claim_txt = nearest_claim(offset)
                    devices.append({"type": label, "offset": offset,
                                     "pct": pct(offset, char_len), "verbatim": text,
                                     "nearest_claim_offset": claim_off,
                                     "nearest_claim_verbatim": claim_txt})
        break  # 3-word phrases only; drop to 2-word gets too noisy to be useful

    # Echo: a distinctive word (>=6 letters, not a stopword) repeated within
    # the same sentence. The loudest, noisiest device here on purpose —
    # see docs/sermon-reading-pass.md for why this one needs the heaviest
    # Stage 2 discount.
    stop = {"because", "something", "everybody", "anything", "another"}
    for i, (offset, text) in enumerate(sentences):
        for w in set(re.findall(r"[A-Za-z']{6,}", text)):
            wl = w.lower()
            if wl in stop:
                continue
            if text.lower().count(wl) >= 2:
                claim_off, claim_txt = nearest_claim(offset)
                devices.append({"type": "echo", "offset": offset,
                                 "pct": pct(offset, char_len), "verbatim": text,
                                 "nearest_claim_offset": claim_off,
                                 "nearest_claim_verbatim": claim_txt})
                break

    devices.sort(key=lambda d: d["offset"])
    return devices


# ---------------------------------------------------------------------------
# Ending
# ---------------------------------------------------------------------------

_DIRECT_ADDRESS_RE = re.compile(
    r"\by'?all\b|\bchurch\b|\bsaints\b|\bsomebody\b|\bfriend\b|\bbeloved\b",
    re.IGNORECASE,
)
_IMPERATIVE_RE = re.compile(
    r"^\s*(?:stand|pray|receive|believe|come|lift|say|reach|close|open|"
    r"repeat|declare|shout|touch|look)\b",
    re.IGNORECASE,
)
_BENEDICTION_RE = re.compile(
    r"in jesus'? name|\bamen\b|go in peace|the lord bless you|"
    r"until we (?:meet|gather) again",
    re.IGNORECASE,
)


def find_ending(body, sentences, char_len, repeated_lines):
    cutoff = int(char_len * 0.9)
    verbatim = body[cutoff:].strip()
    tail_sentences = [(o, t) for o, t in sentences if o >= cutoff]
    tail_offsets = {o for o, _ in tail_sentences}

    repetition = any(
        off in tail_offsets for rl in repeated_lines for off in rl["offsets"]
    )
    direct_address = any(_DIRECT_ADDRESS_RE.search(t) for _, t in tail_sentences)
    cross_reference = bool(SCRIPTURE_RE.search(verbatim))
    imperative = any(_IMPERATIVE_RE.search(t) for _, t in tail_sentences)
    benediction = bool(_BENEDICTION_RE.search(verbatim))

    return {
        "verbatim": verbatim,
        "flags": {
            "repetition": repetition,
            "direct_address": direct_address,
            "cross_reference": cross_reference,
            "imperative": imperative,
            "benediction": benediction,
        },
    }


# ---------------------------------------------------------------------------
# Leak candidates
# ---------------------------------------------------------------------------

_TALKING_DOWN_RE = re.compile(
    r"y'?all (?:not|ain'?t) getting this|everybody wants to go home|"
    r"you'?re not listening|i don'?t have time for this|"
    r"some of you (?:aren'?t|ain'?t) even trying",
    re.IGNORECASE,
)
_PREACHY_RE = re.compile(
    r"i'?m telling you|listen to me|i said what i said|"
    r"i don'?t care what (?:you|anybody) (?:think|says)|hear me (?:good|now)",
    re.IGNORECASE,
)
_EXACERBATING_RE = re.compile(
    r"you should feel|shame on|you ought to|(?:that'?s|that is) on you",
    re.IGNORECASE,
)


def find_leak_candidates(body, sentences, char_len):
    out = []
    for offset, text in sentences:
        kind = None
        if _TALKING_DOWN_RE.search(text):
            kind = "talking_down"
        elif _PREACHY_RE.search(text):
            kind = "preachy"
        elif _EXACERBATING_RE.search(text):
            kind = "exacerbating"
        if kind:
            end = offset + len(text)
            out.append({
                "type": kind, "offset": offset, "pct": pct(offset, char_len),
                "verbatim": text, "next_200_chars": body[end:end + 200].strip(),
            })
    return out


# ---------------------------------------------------------------------------
# Orality markers, by decile
# ---------------------------------------------------------------------------

_SHORT_CLAUSE_RE = re.compile(r"[^,;—]{1,25}(?:,|;|—)")
_INVITATION_RE = re.compile(
    r"say it with me|touch your neighbor|somebody shout|repeat after me|"
    r"turn to (?:your neighbor|somebody)|say (?:amen|yes)",
    re.IGNORECASE,
)


def _by_decile(hits, char_len):
    buckets = [0] * 10
    for offset in hits:
        buckets[decile(offset, char_len)] += 1
    return buckets


def find_orality_markers(body, sentences, char_len, questions, devices):
    direct_address = [o for o, t in sentences if _DIRECT_ADDRESS_RE.search(t)]
    rhetorical = [q["offset"] for q in questions]
    short_clauses = [m.start() for m in _SHORT_CLAUSE_RE.finditer(body)]
    parallelism = [d["offset"] for d in devices if d["type"] in ("anaphora", "epistrophe")]
    invitations = [o for o, t in sentences if _INVITATION_RE.search(t)]

    def entry(hits):
        return {"count": len(hits), "by_decile": _by_decile(hits, char_len)}

    return {
        "direct_address": entry(direct_address),
        "rhetorical_questions": entry(rhetorical),
        "short_clauses": entry(short_clauses),
        "parallelism": entry(parallelism),
        "invitations_to_respond": entry(invitations),
    }


# ---------------------------------------------------------------------------
# Structural map — counts per decile, not prose
# ---------------------------------------------------------------------------

def find_structural_map(char_len, scripture_refs, questions, repeated_lines,
                         devices, leak_candidates):
    map_ = [{"decile": d, "scripture_refs": 0, "questions": 0,
             "repeated_line_hits": 0, "devices": 0, "leak_candidates": 0}
            for d in range(10)]

    def bump(offset, key):
        map_[decile(offset, char_len)][key] += 1

    for r in scripture_refs:
        bump(r["offset"], "scripture_refs")
    for q in questions:
        bump(q["offset"], "questions")
    for rl in repeated_lines:
        for off in rl["offsets"]:
            bump(off, "repeated_line_hits")
    for d in devices:
        bump(d["offset"], "devices")
    for l in leak_candidates:
        bump(l["offset"], "leak_candidates")
    return map_


# ---------------------------------------------------------------------------
# Entry point: run every extractor over one sermon body
# ---------------------------------------------------------------------------

def extract(body):
    """Run every Stage 1 extractor over one sermon body. Returns a dict
    matching the jsonb columns of sermon_reading_pass (minus the id/preacher/
    date columns the caller already has)."""
    char_len = len(body)
    sentences = split_sentences(body)

    scripture_refs = find_scripture_refs(body, sentences, char_len)
    governing_claim = find_governing_claim(sentences, body, char_len)
    tension = find_tension(sentences, char_len)
    target_questions = find_target_questions(sentences, char_len)
    relief_points = find_relief_points(
        sentences, char_len, [r["offset"] for r in scripture_refs]
    )
    repeated_lines = find_repeated_lines(sentences)

    claim_anchors = []
    if governing_claim.get("first_offset") is not None:
        claim_anchors.append((governing_claim["first_offset"], governing_claim["verbatim"]))
    if tension.get("first_offset") is not None:
        claim_anchors.append((tension["first_offset"], tension["verbatim"]))
    claim_anchors.sort(key=lambda a: a[0])

    devices = find_devices(sentences, char_len, claim_anchors)
    ending = find_ending(body, sentences, char_len, repeated_lines)
    leak_candidates = find_leak_candidates(body, sentences, char_len)
    orality_markers = find_orality_markers(body, sentences, char_len, target_questions, devices)
    structural_map = find_structural_map(
        char_len, scripture_refs, target_questions, repeated_lines, devices, leak_candidates
    )

    return {
        "char_len": char_len,
        "governing_claim": governing_claim,
        "tension": tension,
        "target_questions": target_questions,
        "relief_points": relief_points,
        "scripture_refs": scripture_refs,
        "devices": devices,
        "repeated_lines": repeated_lines,
        "ending": ending,
        "leak_candidates": leak_candidates,
        "orality_markers": orality_markers,
        "structural_map": structural_map,
        "extractor_version": EXTRACTOR_VERSION,
    }
