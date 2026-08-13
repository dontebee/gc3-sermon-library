# Pursuit and Trello: what to steal, what to refuse

*PD saw Trello and asked whether the Pursuit Board can look and work like
that. Short answer: it can work like that, and it mostly should not look
like that. Here is the research and the plan.*

## What Trello actually is

Trello is the canonical kanban app: a board, vertical lists, cards you
drag between them. Twenty years of polish have gone into a small set of
ideas, and the ideas are the valuable part.

1. **The card front is a glanceable dossier.** Colored label pills, a
   title, a badge row (due date chip that changes color as the date
   nears, checklist progress like "3/7", comment count), member avatars
   in the corner, an optional cover. You read a card without opening it.
2. **The card back opens over the board.** Clicking a card does not
   navigate away. A detail panel opens in place, you read or edit, you
   press escape, and the board is exactly where you left it. Context is
   never lost.
3. **Drag is the working verb.** Cards tilt when lifted, a placeholder
   shows where they will land, the receiving column highlights. The drop
   zones are generous. On mobile it is long-press to lift. Moving a card
   is the way work gets recorded, not a separate form.
4. **Capture is instant.** "+ Add a card" sits at the foot of every list.
   The composer stays open so you can add five cards in five lines. The
   2025 Trello added an **Inbox**: a holding pen where tasks arrive from
   email and Slack before a human triages them onto the board.
5. **Filtering narrows without navigating.** A filter bar dims what does
   not match. The board never reloads.

One more finding worth PD's attention: Atlassian shipped a big visual
redesign of Trello in May 2025 and the users revolted, loudly, in a
complaint thread hundreds of posts long. What people love about Trello is
the *mechanics*. When the chrome changed and the mechanics did not, they
still revolted. The lesson for us is exact: **make Pursuit work like
Trello. Making it look like Trello is not the prize, and Pursuit already
has its own face**, the sea room and the ship ramp, which is the house's
and validated. Steal the grammar, not the costume.

## What maps straight across

### 1. The card front, upgraded to a dossier

Today a pursuit card shows an avatar, a name, and one meta line. Trello's
lesson is that the front of a card should answer the next question before
it is asked. So:

- **Ship edge** in the ship's color (already built).
- **Visit chip**: "Sun Aug 17", turning amber inside three days and red
  once it is past, exactly like Trello's due badge. A no-show date is the
  single most actionable fact on the board.
- **Source glyph**: ad lead, Plan My Visit, walk-in, prayer request.
- **Streak badge**: "2nd visit" on a returner, because the second visit
  is the number the house watches hardest.
- **Touch count**: how many times the house has reached out, so an
  untouched card is visibly untouched.
- **State dot** once the state axis is live: dormant and inactive render
  as a quiet dot, never as a scarlet letter.

What never appears on a card front, under the discretion ruling: giving,
in any form. A giving-derived reason renders as "gives consistently" on
the card back, for leadership roles, and nowhere else.

### 2. The card back, opened in place

Replace the navigate-away with a Trello-style panel: desktop gets a
centered sheet over a dimmed board, mobile gets a bottom sheet that
slides up. Escape or swipe-down returns to an unmoved board. The full
page at `/pursuit/person/[id]` stays for deep links and shared URLs.

The back carries: the journey timeline (already built), the reasons the
resolver placed them (already stored), quick actions (log a touch, add a
note, pin the ship), and the leadership-gated detail.

### 3. Drag, the real thing

This is the one PD asked for at the very beginning ("lots of drag and
drop workflows") and it is finally due. On the chase board, drag a card
from Planned to Confirmed to Attended. Tilt on lift, placeholder in the
receiving stack, column highlight, long-press with a small haptic on
phones, and full keyboard support (space lifts, arrows move, space
drops) so it passes accessibility.

Every drop writes `pursuit_stage_events` with who moved it and when. The
drag is not decoration; it is the fastest possible way for a human to
testify "she confirmed" or "they came".

### 4. Capture at the foot of the column

"+ Add a person" at the foot of every stage. Type a name, optionally a
phone, enter, done, composer stays open. A greeter at the door records a
walk-in in four seconds on a phone. Creates the person with
`source: 'manual'` and a card in that stage.

### 5. The Inbox column

Trello's 2025 Inbox, translated: a first column named **Arrivals** that
holds what the machines brought in overnight, new ad leads from the Meta
mirror, prayer requests, ChurchFunnels contacts, each waiting for a
human to drag it into the chase or archive it as not-a-person. Triage
becomes a drag instead of a query. Nothing enters the board unseen.

### 6. The filter bar

One row above the board: by ship, by source, by "has a visit this week",
by "untouched". Dims non-matching cards in place, never reloads, and a
leader's filter choice persists per device.

## Where Trello's grammar must bend to the house

**Dragging between ships is not free.** In Trello a column is just a
place; moving a card costs nothing and means nothing. In Pursuit the
ships are evidence: the resolver computes them from rules PD set, and a
hand cannot simply drag someone to Partnership. But the rules already
contain the answer: **a human pin beats every rule.** So the gesture
stays and gains weight. Dragging a person onto another ship opens a
confirm: "Pin Marcus to Partnership? The resolver will stop moving him.
Recorded: pinned by you, today." Cancel is one tap. Trello's gesture,
wearing the house's rules.

**Stages drag freely, ships drag solemnly.** The chase stages
(planned, confirmed, attended, returned) are testimony about what
happened, and any shepherd can testify. The ships are judgement, and
judgement takes a confirm and leaves a record.

**Labels mean things here.** Trello labels are freeform colored tags.
Ours are mostly machine-set and rule-derived: the A-flags, the state
dots, the streak. One small hand-set vocabulary is worth adding for
leaders (call me, Spanish service, new believer, needs prayer), stored
as touches so they carry who and when. A board where anyone can invent
labels becomes a board nobody can read.

**No public boards, no sharing, no covers pulled from social media.**
Access stays role-gated as built. Avatars stay initials until a PCO
photo sync is deliberately decided.

## The build, phased

| Phase | What | Weight |
|---|---|---|
| B1 | Card front dossier: chips, glyphs, streaks, touch count | CSS + server components, no new deps |
| B2 | Card back in place: desktop sheet, mobile bottom sheet | Next.js parallel/intercepted route |
| B3 | Drag: stages free, ships pinned, keyboard + touch | `@dnd-kit` (react-beautiful-dnd is deprecated), server actions, optimistic UI |
| B4 | Capture composer + Arrivals column | server action + Meta mirror feed |
| B5 | Filter bar + per-role default lenses | client state, persisted per device |

Mobile-first throughout, per the standard already adopted: columns
snap-scroll one per swipe on phones the way Trello's own mobile app
does, bottom sheets not modals under 720px, 44pt targets, `:active`
states, overscroll contained.

B3 is the only phase with a real dependency decision. `@dnd-kit` is the
right one: actively maintained, touch and keyboard sensors built in,
and it does not fight React server components as long as the board
hydrates as one client island with server-fetched initial data.

## What this does not touch

The rule engine, the resolver, the state axis, and the Pathways line all
sit under this UI unchanged. Nothing in the board sends anything to
anybody. A drag writes a stage event or a pin, and that is the whole of
its power.
