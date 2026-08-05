# GodChasers sermon library — house rules

This repo runs scheduled backend jobs. **It does not email members.**

## Vocabulary. Get this right.

**Journeys** = Growth Track. GATHER, GROW, GO. The `gt_*` tables.

**Pathways** = Next Steps. Everything else the house sends a member.

PD will correct you if you swap them. When you mean the Next Steps system,
say Pathways.

## The hard rule

**Nothing in this repo sends to a member.** Member-facing email belongs to the
Pathways engine in `gc3-intranet` (`src/lib/pathways/`), which has the on/off
switch, the shared suppression list, unsubscribe links, rate limits, editable
rules, and an admin page.

What legitimately lives here:

- syncing Planning Center giving into `giving_gifts`
- the Monday digest — one email, to PD, not to members
- the weekly YouTube sermon pull and enrichment

**Why the rule exists.** On 2026-08-05 `engagement_nudges.py` sent 30
monthly-partner invitations to donors who had given $38,759 in the previous 90
days — including six staff and people already giving weekly — while every
Pathway was switched off at `/admin/pathways`. It ran because it was a second
emailing system with its own logic, its own tables and no switch. It even
reimplemented `first_gift`, which already existed as a Pathway.

The emails opened "friend," (names live in PCO **People**, and the code only
asked **Giving**), said "I have noticed your faithfulness in giving" (the house
style forbids the surveillance voice), and carried no unsubscribe.

If you are about to add a `send_email` call to this repo, you are about to
repeat that. Build it as a Pathway instead.

## How the rule is enforced

`send_email()` refuses any address that is not `DIGEST_TO` and says so in the
log. The machinery for member email — the letter template, the pathway copy,
unsubscribe minting, suppression loading — was deleted rather than left lying
around, so there is nothing to accidentally call.

If you find yourself rebuilding any of it here, that is the signal to stop and
build a Pathway instead.

Manual `workflow_dispatch` runs default to **dry run**. Untick it deliberately.

## What this job owes the Pathways engine

`giving_gifts.donor_email` and `donor_name`. Planning Center **Giving** returns
a person id but never a name or an address, and the engine enrols `first_gift`
and `monthly_partner` straight off this table. If the backfill from **People**
stops working, those pathways silently reach nobody. It is the quietest way
this job can fail.

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
