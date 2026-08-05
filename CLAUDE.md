# GodChasers sermon library — house rules

This repo runs scheduled backend jobs. **It does not email members.**

## Vocabulary. Get this right.

**Journeys** = Growth Track. GATHER, GROW, GO. The `gt_*` tables.

**Pathways** = Next Steps. Everything else the house sends a member.

PD will correct you if you swap them. When you mean the Next Steps system,
say Pathways.

## The hard rule

**Nothing in this repo sends to a member.** Member-facing email belongs to the
Pathways engine in `gc3-intranet` (`src/lib/journeys/`), which has the on/off
switch, the shared suppression list, unsubscribe links, rate limits, editable
rules, and an admin page.

What legitimately lives here:

- syncing Planning Center giving into `giving_gifts`
- the Monday digest — one email, to PD, not to members
- the weekly YouTube sermon pull and enrichment

**Why the rule exists.** On 2026-08-05 `engagement_nudges.py` sent 30
monthly-partner invitations to donors who had given $38,759 in the previous 90
days — including six staff and people already giving weekly — while every
Pathway was switched off at `/admin/journeys`. It ran because it was a second
emailing system with its own logic, its own tables and no switch. It even
reimplemented `first_gift`, which already existed as a Pathway.

The emails opened "friend," (names live in PCO **People**, and the code only
asked **Giving**), said "I have noticed your faithfulness in giving" (the house
style forbids the surveillance voice), and carried no unsubscribe.

If you are about to add a `send_email` call to this repo, you are about to
repeat that. Build it as a Pathway instead.

## If a send survives here anyway

Every member-facing send must, without exception:

- call `journey_active(key)` first — it **fails closed**: unknown pathway,
  missing row, master switch off, or database unreachable all mean send nothing
- check `load_suppression()`, the same `email_recipients` list the intranet
  uses, so an unsubscribe anywhere means everywhere
- pass `unsub=` to both `letter()` and `send_email()`
- respect `MAX_EMAILS` and the per-kind cooldown

Manual `workflow_dispatch` runs default to **dry run**. Untick it deliberately.

## House style for anything a member reads

- short. Around 60 to 90 words.
- Scripture lands AFTER the point, one line, usually KJV.
- **God does the seeing, not the pastor. No surveillance voice.**
- the body asks for nothing. The P.S. carries the next step.

## Facts worth not rediscovering

- One Supabase project, `eibrykdamgyoylnqknao`, holds everything.
- Credentials: `gc3_env.py` accepts either naming (`NEXT_PUBLIC_SUPABASE_URL`
  / `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_SERVICE_KEY`) and
  validates the key's shape at startup.
- Secrets come from Doppler (`gc3-intranet` project, `prd` config) via its
  GitHub Actions sync. They arrive as **Secrets**, not Variables.
- Planning Center is several products. **Giving** has donations and person
  ids; **People** has names and emails. Giving will not give you a name.
