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
retried once; if it fails twice the **original** chunk is kept. So a stored
row can differ from its source in punctuation, capitalization and whitespace,
and in nothing else. Not a spelling. Not a contraction. Not a repeated phrase.

Apostrophes are deleted rather than compared because inserting them is
harmless and models do it reflexively: `dont` and `don't` normalize alike.

`verified` is true only when every chunk of that sermon passed. The reading
pass reads `WHERE verified` and ignores the rest.

The verifier is tested against the cases that would actually hurt, and
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
deliberate, and a model's instinct is to tidy it away. This catches that.

## Cost

Roughly 20M characters remain, about 5.5M input tokens and a similar number
out. At list prices, before any thinking tokens:

| model | rough cost |
|---|---:|
| `claude-opus-5` | ~$155 |
| `claude-sonnet-5` | ~$62 |
| `claude-haiku-4-5` | ~$31 |

`claude-opus-5` is the default because it is the house default, not because
this task demands it. The job runs at `effort: "low"` — inserting periods is
not a reasoning problem — and the verifier catches a weaker model's mistakes
rather than shipping them, so a cheaper tier is a reasonable trade. That is
PD's call, not the script's: `--model` takes any of the three, and the
workflow offers all three in a dropdown.

Run `--survey` first. It counts the remaining work and prices it at every
tier without calling the model once.

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
