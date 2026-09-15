"""
Put punctuation back into transcripts that arrived without any.

Roughly 82% of exemplar_sermons and 31% of sermons carry no terminal
punctuation at all — auto-caption scrapes, one unbroken lowercase run of
words. Stage 1 of the reading pass can still read those, but only through a
fixed-word-window fallback, so every offset it reports is an approximation
and every rhetorical question is invisible (there is no "?" to find). Worse
for the reading pass's actual purpose: the exemplar corpus is 82% unpunctuated
and PD's is 31%, so any comparison between them partly measures who got the
better transcription.

This fixes the input rather than the reader.

    python3 restore_punctuation.py --survey
    python3 restore_punctuation.py --limit 3            # dry run, prints diffs
    python3 restore_punctuation.py --limit 3 --apply
    python3 restore_punctuation.py --apply              # the whole backlog

WHAT IT WILL NOT DO
-------------------
It will not change a word. Not a spelling, not a contraction, not a
transcription error, not "y'all" into "you all". The model is told that, and
then it is checked, because being told is not a guarantee:

    normalize(text) = lowercase, drop apostrophes, every other run of
                      non-alphanumerics becomes one space

If normalize(input) != normalize(output), the chunk is rejected and retried;
if it fails twice the ORIGINAL chunk is kept. So a stored row can differ from
its source in punctuation, capitalization and whitespace, and in nothing
else. That is a mechanical guarantee, not a promise about model behaviour.

It also never writes to `sermons` or `exemplar_sermons`. Output goes to
`sermon_text_restored`. See that schema for why.
"""
import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import gc3_env

RESTORER_VERSION = "restore-punctuation-1.0.0"

# Opus 5 is the house default. This is a mechanical task, so it runs at
# effort "low" — see the request below — but the model choice stays PD's:
# --model swaps it, and --survey prints what each tier would cost.
DEFAULT_MODEL = "claude-opus-5"

# Below this many terminal marks per 1,000 characters, a body is treated as
# unpunctuated. Same threshold the extractor uses; measured against real rows,
# where punctuated sermons run 20+ and unpunctuated ones run 0–0.1.
SPARSE_THRESHOLD = 2.0

# Words per chunk. Small enough that one bad chunk is cheap to redo and that
# output stays well inside max_tokens, large enough that sentence boundaries
# at the seams are a rounding error.
WORDS_PER_CHUNK = 1200

SYSTEM_PROMPT = """\
You restore punctuation to sermon transcripts that were produced by automatic \
speech recognition and arrived with none.

You may ONLY:
- insert the characters . , ? ! ; : and -
- change the capitalization of existing letters
- insert paragraph breaks between clear shifts in thought

You may NOT, under any circumstances:
- add, delete, reorder, or substitute any word
- correct spelling, grammar, or obvious transcription errors
- add apostrophes to words that lack them
- expand or contract anything ("yall" stays "yall", "dont" stays "dont")
- add commentary, headings, speaker labels, or explanation

The transcript may contain mistakes, repeated words, false starts and \
half-sentences. Leave every one of them exactly as it is. A preacher's \
repetition is often deliberate. Your job is only to mark where the sentences \
end, so the words can be read.

Output the punctuated text and nothing else."""

USER_TEMPLATE = """\
Restore punctuation to this transcript excerpt. Same words, in the same \
order, with punctuation and capitalization added.

<transcript>
{chunk}
</transcript>"""

RETRY_SUFFIX = """

Your previous attempt changed at least one word. Return the SAME WORDS in the \
SAME ORDER. Add only punctuation and capitalization."""


# ---------------------------------------------------------------------------
# The guarantee
# ---------------------------------------------------------------------------

_APOSTROPHES = re.compile(r"['‘’ʼ]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text):
    """The word stream, stripped of everything punctuation can express.

    Lowercase, apostrophes deleted outright (so "dont" and "don't" agree —
    inserting an apostrophe is harmless and the model does it reflexively),
    every other run of non-alphanumerics collapsed to a single space.

    Two texts with the same normalization contain the same letters and digits
    in the same order. Nothing else survives, which is the point: it is
    exactly the set of changes punctuation restoration is allowed to make.
    """
    t = _APOSTROPHES.sub("", text.lower())
    return " ".join(_NON_ALNUM.sub(" ", t).split())


def words_preserved(source, restored):
    return normalize(source) == normalize(restored)


def first_difference(source, restored):
    """Where the two word streams diverge, for the log. Returns a short
    human-readable string, not a diff — enough to see whether the model
    dropped a word or invented one."""
    a, b = normalize(source).split(), normalize(restored).split()
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            lo = max(0, i - 5)
            return (f"word {i}: source ...{' '.join(a[lo:i + 3])}... "
                    f"vs restored ...{' '.join(b[lo:i + 3])}...")
    if len(a) != len(b):
        longer, shorter = (a, b) if len(a) > len(b) else (b, a)
        who = "source" if len(a) > len(b) else "restored"
        return f"{who} has {len(longer) - len(shorter)} extra words at the end"
    return "identical (should not happen)"


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_words(body, n=WORDS_PER_CHUNK):
    """Split on whitespace into n-word pieces. Offsets do not matter here —
    the restored text is rebuilt by joining, and the reading pass re-derives
    its own offsets from the result."""
    words = body.split()
    return [" ".join(words[i:i + n]) for i in range(0, len(words), n)]


# ---------------------------------------------------------------------------
# The model call
# ---------------------------------------------------------------------------

def restore_chunk(client, model, chunk, attempts=2):
    """Punctuate one chunk, verified. Returns (text, ok).

    On failure the ORIGINAL chunk comes back with ok=False, so a caller that
    ignores the flag still never stores altered words.
    """
    prompt = USER_TEMPLATE.format(chunk=chunk)
    for attempt in range(attempts):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                # A mechanical task: adaptive thinking on (the default on
                # Opus 5) but at the lowest effort, so it does not spend
                # output tokens reasoning about where commas go.
                output_config={"effort": "low"},
                messages=[{"role": "user",
                           "content": prompt + (RETRY_SUFFIX if attempt else "")}],
            )
        except Exception as exc:                      # noqa: BLE001 — logged, then retried
            print(f"    api error ({type(exc).__name__}): {exc}", flush=True)
            time.sleep(2 ** attempt)
            continue

        if response.stop_reason == "refusal":
            print("    refused; keeping the original chunk", flush=True)
            return chunk, False

        out = "".join(b.text for b in response.content if b.type == "text").strip()
        if not out:
            continue
        if words_preserved(chunk, out):
            return out, True
        print(f"    attempt {attempt + 1} changed words — {first_difference(chunk, out)}",
              flush=True)

    return chunk, False


def restore_body(client, model, body):
    """Punctuate a whole sermon. Returns (text, chunks_total, chunks_verified)."""
    chunks = chunk_words(body)
    out, ok_count = [], 0
    for chunk in chunks:
        text, ok = restore_chunk(client, model, chunk)
        out.append(text)
        ok_count += int(ok)
    return "\n\n".join(out), len(chunks), ok_count


# ---------------------------------------------------------------------------
# Reading the corpus
# ---------------------------------------------------------------------------

def _rest_headers():
    key = gc3_env.service_key()
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"}


def density(body):
    if not body:
        return 0.0
    return 1000.0 * sum(body.count(c) for c in ".?!") / len(body)


def fetch_sparse(source, limit=None, redo=False):
    """Unpunctuated sermons that have no verified restoration yet."""
    import requests

    base = gc3_env.supabase_url() + "/rest/v1/"
    headers = _rest_headers()
    table, id_cols = (("exemplar_sermons", "id,preacher,title,body")
                      if source == "exemplar" else
                      ("sermons", "id,speaker,title,body"))
    params = {"select": id_cols, "order": "id.asc"}
    if source == "exemplar":
        params["calibration_eligible"] = "eq.true"

    rows, offset, page = [], 0, 1000
    while True:
        r = requests.get(base + table,
                         headers={**headers, "Range-Unit": "items",
                                  "Range": f"{offset}-{offset + page - 1}"},
                         params=params, timeout=120)
        if r.status_code >= 300:
            raise SystemExit(f"ERROR: could not read {table} ({r.status_code}): {r.text[:300]}")
        chunk = r.json()
        rows.extend(chunk)
        if len(chunk) < page:
            break
        offset += page

    sparse = [r for r in rows
              if (r.get("body") or "").strip() and density(r["body"]) < SPARSE_THRESHOLD]

    if not redo:
        done = fetch_already_restored(source)
        sparse = [r for r in sparse if r["id"] not in done]

    return sparse[:limit] if limit else sparse


def fetch_already_restored(source):
    """ids with a verified restoration, so a re-run resumes instead of repeating."""
    import requests

    r = requests.get(gc3_env.supabase_url() + "/rest/v1/sermon_text_restored",
                     headers=_rest_headers(),
                     params={"select": "source_id", "source": f"eq.{source}",
                             "verified": "is.true"},
                     timeout=60)
    if r.status_code >= 300:
        # The table may not exist yet on a first run; that is not fatal.
        print(f"NOTE: could not read sermon_text_restored ({r.status_code}); "
              "treating everything as unrestored.")
        return set()
    return {row["source_id"] for row in r.json()}


def write_rows(records, batch_size=5):
    import requests

    url = gc3_env.supabase_url() + "/rest/v1/sermon_text_restored"
    headers = {**_rest_headers(),
               "Prefer": "resolution=merge-duplicates,return=minimal"}
    written = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        r = requests.post(url, headers=headers,
                          params={"on_conflict": "source,source_id"},
                          data=json.dumps(batch), timeout=180)
        if r.status_code >= 300:
            raise SystemExit(f"ERROR: insert failed ({r.status_code}): {r.text[:300]}")
        written += len(batch)
        print(f"  ... stored {written}/{len(records)}", flush=True)
    return written


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

# $ per 1M tokens, input/output. From the Claude API reference, 2026-06-24.
PRICING = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def estimate_cost(total_chars, model):
    """Rough, and labelled as rough. ~3.6 chars/token for English prose; the
    output is the input plus punctuation, so a little larger. Thinking at
    effort low adds some output tokens this does not try to predict."""
    in_tok = total_chars / 3.6
    out_tok = in_tok * 1.08
    rate_in, rate_out = PRICING.get(model, PRICING[DEFAULT_MODEL])
    return (in_tok * rate_in + out_tok * rate_out) / 1_000_000


def survey(sources):
    total_chars = 0
    for src in sources:
        rows = fetch_sparse(src, redo=True)
        done = fetch_already_restored(src)
        chars = sum(len(r["body"]) for r in rows)
        total_chars += sum(len(r["body"]) for r in rows if r["id"] not in done)
        print(f"{src}: {len(rows)} unpunctuated sermons, {len(done)} already restored, "
              f"{len(rows) - len([r for r in rows if r['id'] in done])} to do. "
              f"{chars:,} characters total.")
    print(f"\nRemaining work: {total_chars:,} characters.")
    print("Rough cost to restore, by model (thinking not included):")
    for model in PRICING:
        print(f"  {model:20} ${estimate_cost(total_chars, model):,.2f}")


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=["exemplar", "pd", "both"], default="both")
    ap.add_argument("--limit", type=int, default=None, help="cap sermons per corpus")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=4, help="sermons in flight at once")
    ap.add_argument("--survey", action="store_true", help="count and price the work, do nothing")
    ap.add_argument("--redo", action="store_true", help="include sermons already restored")
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    args = ap.parse_args()

    sources = ["exemplar", "pd"] if args.source == "both" else [args.source]

    if args.survey:
        survey(sources)
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ERROR: ANTHROPIC_API_KEY is not set. It is in Doppler, "
                         "and the workflow passes it through.")
    import anthropic
    client = anthropic.Anthropic()

    work = []
    for src in sources:
        for row in fetch_sparse(src, args.limit, args.redo):
            work.append((src, row))
    if not work:
        print("Nothing to restore.")
        return

    chars = sum(len(r["body"]) for _, r in work)
    print(f"{len(work)} sermons, {chars:,} characters. "
          f"Model {args.model}. Rough cost ${estimate_cost(chars, args.model):,.2f}.\n")

    records, failures = [], []

    def one(item):
        src, row = item
        who = row.get("preacher") or row.get("speaker") or "?"
        restored, total, ok = restore_body(client, args.model, row["body"])
        flag = "ok " if ok == total else "PARTIAL"
        print(f"  [{flag}] {src} {row['id']:5} {who[:18]:18} "
              f"{row['title'][:40]:40} {ok}/{total} chunks", flush=True)
        return {
            "source": src, "source_id": row["id"],
            "body_restored": restored,
            "verified": ok == total,
            "chunks_total": total, "chunks_verified": ok,
            "restored_by": args.model, "restorer_version": RESTORER_VERSION,
            "char_len_source": len(row["body"]),
            "char_len_restored": len(restored),
        }

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for rec in pool.map(one, work):
            (records if rec["verified"] else failures).append(rec)

    print(f"\n{len(records)} fully verified, {len(failures)} partial.")
    if records:
        sample = records[0]
        print(f"\nSample ({sample['source']} {sample['source_id']}), first 400 chars:")
        print("  " + sample["body_restored"][:400].replace("\n", "\n  "))

    if not args.apply:
        print("\nDRY RUN. Nothing written. Pass --apply to store.")
        return

    # Partial rows are stored too, with verified=false, so a later run can see
    # what to retry. Readers filter on verified.
    written = write_rows(records + failures)
    print(f"\nWrote {written} rows ({len(records)} verified).")


if __name__ == "__main__":
    main()
