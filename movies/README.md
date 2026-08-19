# Marquee — your movie shelf 🎬

A personal movie website that lives in one file (`index.html`). It lets you:

- **Rate movies you've seen** — tap the stars, done. Tap the same star again to clear.
- **Mark movies you own** — and note *where* you own them (Google Play / YouTube,
  Apple TV, Prime Video, disc, other).
- **Get picks chosen for your taste, refreshed every day**:
  - *Picked for you tonight* — based on what you rated 4–5 stars
  - *Hidden gems you might've missed* — lesser-known movies that fit your taste
    (the "I almost missed *Tuner*" shelf)
  - *New & worth a look* — releases from the last ~3 months sorted for you,
    so nothing slips by
  - *Keep training my taste* — a daily queue of movies to quick-rate
    (or tap "Haven't seen it" to skip)
- **Add a note** on any movie ("loved the tension, hated the ending") — optional;
  stars alone are enough.
- **See where to stream / rent / buy** any movie (from TMDB's JustWatch data).
- **Search every movie ever made** via TMDB, the open movie database.

Everything you rate and own is stored in your browser (with one-tap
export/restore backup in Settings), so there's no account and no server.

## Getting started

1. Open `index.html` in any browser — or better, deploy it (see below) so it's
   on your phone too.
2. First launch walks you through getting a **free TMDB API key** (~2 minutes at
   themoviedb.org → Settings → API). Paste it once; it stays in your browser.
3. Rate a handful of movies on the **Tonight** tab. After ~3 ratings the
   recommendation shelves light up, and they sharpen with every rating.

## "How do I show you which movies I own?"

Google Play/YouTube and Apple don't let outside apps read your purchase
library — there's no API for it. The practical route is built into
**Settings → Import the movies I own**:

1. **Google Play / YouTube:** go to `youtube.com/feed/purchases` (or Google
   Takeout → "Google Play Movies & TV") and copy your titles.
2. **Apple TV:** TV app → Library → Purchased, copy the titles.
3. Paste them into the import box (one per line, year optional like
   `Heat (1995)`), pick which store they came from, and Marquee matches each
   one to the right movie with poster and all. Unmatched lines are flagged so
   you can fix them.

## Deploying it as a real website

Any static host works — it's a single HTML file:

- **Vercel:** `npx vercel deploy movies/` (or drag the folder into vercel.com/new)
- **GitHub Pages:** repo Settings → Pages → serve from the branch, then visit
  `/movies/`
- **Netlify:** drag the `movies` folder onto app.netlify.com/drop

Your data is per-browser (localStorage). Use **Settings → Export backup** to
move your shelf between phone and computer, or after clearing browser data.

## Notes for future work

- "Push me a suggestion every morning" needs a small server or scheduled job —
  today, picks refresh daily whenever you open the site (deterministic by date).
- Ratings are whole stars 1–5 by design: fast to tap, easy to reason about.
- All TMDB responses are cached in localStorage (~24h) to keep it fast and
  gentle on the free API tier.
