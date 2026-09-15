# Restoring punctuation on unpunctuated transcripts

## The problem, measured

Most of the corpus arrived from automatic captions as one unbroken lowercase
run of words. No periods, no question marks, nothing:

| corpus | sermons | no terminal punctuation | share |
|---|---:|---:|---:|
| `exemplar_sermons` (calibration-eligible) | 624 | 509 | **81.6%** |
| `sermons` (PD) | 1,250 | 392 | **31.4%** |

Per preacher, it splits almost cleanly by source:

| preacher | sermons | punctuated |
|---|---:|---:|
| T.D. Jakes | 242 | 0% |
| Dharius Daniels | 218 | 0% |
| Steven Furtick | 124 | 84% |
| Tolan Morgan | 21 | 48% |

Two consequences, and the second is the serious one.

**It degrades Stage 1.** With no terminal punctuation the sentence splitter
falls back to fixed 22-word windows, so every offset is an approximation and
`target_questions` comes back empty no matter how many rhetorical questions
the sermon actually contains — there is no `?` to match.

**It biases the comparison the reading pass exists to make.** The exemplar
corpus is 82% unpunctuated and PD's is 31%. Compare the two as they stand and
part of what you measure is who got the better transcription. Jakes and
Daniels would show zero detectable questions; PD would show plenty. That is a
fact about caption quality, not about preaching, and it would read as a
finding.

## What this does

`restore_punctuation.py` sends each unpunctuated body to Claude, which inserts
punctuation and capitalization and changes nothing else. Output goes to a new
table, `sermon_text_restored`. Then `sermon_reading_pass.py` prefers the
restored text when a verified row exists.

## Why it does not write to `sermons` or `exemplar_sermons`

Two reasons, either one sufficient.

Both CLAUDE.md files say never write to those tables, and the exemplar ingest
spec says "Leave the words alone. Do not punctuate, do not capitalize, do not
'improve.'" Those still hold. This does not violate them: the source bodies
are untouched and the restored text sits beside them, marked as derived.

Mechanically, `sermons.body` feeds a generated `fts` tsvector and sits next to
an `embedding`. Rewriting 392 bodies in place would silently re-index a third
of PD's corpus, and a polluted similarity search cannot be un-run.

## The guarantee, and why it is a guarantee

The model is told not to change a word. Being told is not a guarantee, so
every chunk is checked after it comes back:

```
normalize(text) = lowercase
                  delete apostrophes outright
                  every other run of non-alphanumerics -> one space
```

If `normalize(source) != normalize(restored)`, the chunk is rejected and
retried with the offending span quoted back; after three attempts the
**original** chunk is kept. So a stored row can differ from its source in
punctuation, capitalization and whitespace, and in nothing else. Not a
spelling. Not a contraction. Not a repeated phrase.

Apostrophes are deleted rather than compared because inserting them is
harmless and models do it reflexively: `dont` and `don't` normalize alike.

### What `verified` means (and does not)

`verified` is true when **every** chunk of that sermon got punctuated. It is
**not** a trust gate. Word safety is unconditional: a chunk that came back
altered is discarded in favour of its original text *before anything is
stored*, so every row holds exactly the source's words whatever the flag says.
A `verified = false` row is simply punctuated in fewer places.

The reading pass therefore reads **all** restored rows, not just verified
ones. Filtering on `verified` was the original design and it was wrong: on the
first real run 13 of 17 chunks came back clean, but the four failures were
spread across all three sermons, so a verified-only filter would have thrown
away every sermon and read the raw bodies instead. Five-sixths punctuated
beats not punctuated.

### What the model actually tries to do

From the first run against real transcripts — every rejection was an attempted
improvement:

| source (what was said) | the model's "fix" |
|---|---|
| `what what stood out` | `what stood out` |
| `theyre in ducting` | `theyre inducting` |
| `and i kept spelling it ar e h` | `...it r e h` |
| `let you which is a` | `let you like some of` |

The first is Furtick stuttering. The third is him spelling a word out loud.
Both are the preaching, and both would have been quietly tidied away. Four of
six failures repeated the identical edit on a second attempt, which is why the
retry now quotes the exact span back rather than saying "you changed
something".

The verifier is also tested against synthetic cases that would hurt, and
rejects all of them:

| case | verdict |
|---|---|
| `"he is working he is working he is working"` → `"He is working."` | rejected |
| `"i i i want to tell you"` → `"I want to tell you."` | rejected |
| `"the potter formed it"` → `"The potter shaped it"` | rejected |
| `"psalm 51 verse 10"` → `"Psalm 51, verse 12."` | rejected |
| appended `[Note: transcript unclear]` | rejected |
| `"yall dont know"` → `"Y'all don't know."` | accepted |

The first two matter most for preaching. A preacher's repetition is usually
deliberate, and a model's instinct is to tidy it away. This catches that, and
the live run above confirmed it catches it on real text too.

## Cost

Measured by `--survey` against the live corpus on 2026-09-15, not estimated:

| corpus | sermons to restore | characters |
|---|---:|---:|
| `exemplar_sermons` | 509 | 20,471,380 |
| `sermons` (PD) | 392 | 11,913,808 |
| **total** | **901** | **32,385,188** |

At list prices, before any thinking tokens:

| model | cost |
|---|---:|
| `claude-opus-5` | ~$288 |
| `claude-sonnet-5` | ~$115 |
| `claude-haiku-4-5` | ~$58 |

(An earlier draft of this file guessed 20M characters and so quoted roughly
half these numbers. The corpus is 32.4M. Run `--survey` rather than trusting
a remembered figure — it is free and it reads the live tables.)

`claude-opus-5` is the default because it is the house default, not because
this task demands it. The job runs at `effort: "low"` — inserting periods is
not a reasoning problem — and the verifier catches a weaker model's mistakes
rather than shipping them, so a cheaper tier is a reasonable trade. That is
PD's call, not the script's: `--model` takes any of the three, and the
workflow offers all three in a dropdown.

Run `--survey` first. It counts the remaining work and prices it at every
tier without calling the model once.

Measured on the first run: 3 exemplar sermons, 95,412 characters, 17 chunks,
about 2m40s wall clock at 4 workers, and the script's own estimate for that
slice was $0.85. Scaling that to 32.4M characters puts the full run at roughly
15 hours of wall clock at 4 workers — raise `--workers` for the real thing,
and note the workflow's 350-minute timeout will not fit it in one go. It
resumes, so several runs is fine.

## Running it

```
# count and price the work; calls no model
python3 restore_punctuation.py --survey

# three sermons, printed, nothing written
python3 restore_punctuation.py --limit 3

# three sermons, stored
python3 restore_punctuation.py --limit 3 --apply

# the whole backlog
python3 restore_punctuation.py --apply
```

Or the Actions tab: `restore_punctuation.yml`. Dry run is on by default and
the limit defaults to `3` rather than blank, because an accidental unlimited
run is a real bill. Blank it deliberately.

It resumes. Sermons with a verified row are skipped on the next run, so a job
that dies halfway costs only what it already spent.

## After restoring

Re-run the reading pass so Stage 1 reads the repaired text:

```
python3 sermon_reading_pass.py --apply
```

`sermon_reading_pass.py --raw-bodies` forces the original bodies, which is how
to compare a restored run against the pre-restoration one.

Expect `punctuation_quality` to flip from `sparse_punctuation` to `normal` for
restored sermons, `target_questions` to stop being empty, and offsets to mean
what they say.
