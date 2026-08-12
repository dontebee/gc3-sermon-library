"""Weekly Meta ads performance report: pull insights, analyze, recommend.

Figuring out which ads work is a data problem, and the data is already paid
for: every impression Meta serves is logged in the Marketing API. This job
pulls that data weekly, keeps a daily history in meta_ad_insights, compares
this week to last week, and turns the differences into plain recommendations
(rotate this creative, pause that ad, shift budget toward the winner). The
findings go to the Action log here and into meta_ad_recommendations, where
the Monday digest (engagement_nudges.py) picks them up for the Lead Pastor.

Read-only, on purpose. This job holds an ads_read token and never writes to
the ad account: no budget changes, no pausing, no new campaigns. The change
itself stays a human decision made in Ads Manager; this job makes sure it is
an informed one. If automated changes ever feel worth it, they should start
the way the engagement job did: behind a dry run, report-only, earning trust.

The other hard line: never upload member or donor data from this database to
Meta (no Custom Audiences from giving_gifts, gt_profiles, or anywhere else).
That is house data used to target the house, the same class of mistake as
2026-08-05. Ads aim outward, at people not yet in the house. A seed list for
a Lookalike audience would be PD's deliberate, hand-approved decision, never
a job's.

Env vars:
  META_ACCESS_TOKEN      Marketing API token with ads_read. Use a System User
                         token (business.facebook.com > Business settings >
                         Users > System users): user tokens expire about every
                         60 days, system user tokens do not.
  META_AD_ACCOUNT_ID     the ad account id, with or without the act_ prefix
                         (it is the act=... number in the Ads Manager URL)
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   the database (the
                         NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_KEY
                         spellings also work)
Optional:
  ANTHROPIC_API_KEY      adds a short written strategy note on top of the
                         rule-based flags (same key the sermon enrichment uses)
  DRY_RUN                "1" to fetch, analyze and print, but write nothing

Without the two META_ secrets the job prints setup instructions and exits
cleanly, so this can merge and schedule before the account is connected.
"""
import json
import os
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

import gc3_env

# Ad names can carry emoji, same as sermon titles. Keep stdout UTF-8 safe.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

META_API_VERSION = "v23.0"
GRAPH = f"https://graph.facebook.com/{META_API_VERSION}"

LOOKBACK_DAYS = 28               # daily history window refreshed each run
MIN_IMPRESSIONS_TO_JUDGE = 1000  # below this a week is noise, not signal
FATIGUE_FREQUENCY = 3.0          # avg views per person in 7 days before "rotate"
CTR_DROP_ALERT = 0.30            # 30% week-over-week click-rate drop
LOW_CTR_FLOOR = 0.6              # percent; also flagged under half the account median
COST_SPIKE_ALERT = 0.30          # 30% week-over-week cost-per-result rise
MIN_RESULTS_TO_COMPARE = 5       # cost-per-result math needs at least this many
STRATEGY_MODEL = "claude-sonnet-4-6"  # same tier the sermon enrichment uses

# Which action counts as "the result", most valuable first. Meta reports many
# action types per ad; the first of these present is what the ad is considered
# to be for. Tune this list as campaign objectives change.
RESULT_PRIORITY = [
    "lead",
    "onsite_conversion.messaging_conversation_started_7d",
    "landing_page_view",
    "link_click",
    "post_engagement",
    "video_view",
    "page_engagement",
]

SUPABASE_URL = gc3_env.supabase_url()
SERVICE_KEY = gc3_env.service_key()
META_TOKEN = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
_raw_acct = (os.environ.get("META_AD_ACCOUNT_ID") or "").strip()
AD_ACCOUNT = _raw_acct if _raw_acct.startswith("act_") else (f"act_{_raw_acct}" if _raw_acct else "")
ANTHROPIC_API_KEY = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
DRY_RUN = os.environ.get("DRY_RUN", "").strip() in ("1", "true", "yes")

try:
    from supabase import create_client
except ImportError:
    print("ERROR: 'supabase' not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SERVICE_KEY)


# ---------------------------------------------------------------- graph api

def meta_get(path_or_url, params=None):
    """GET from the Graph API with retry on throttling and server errors.

    Meta signals throttling as HTTP 400 with error codes 4, 17 or 32 rather
    than a clean 429, so the retry decision reads the error body, not just the
    status line. Code 190 is an invalid or expired token, which retrying will
    never fix, so it gets an explanation and a hard stop instead.
    """
    url = path_or_url if path_or_url.startswith("http") else f"{GRAPH}/{path_or_url}"
    p = dict(params or {})
    if not path_or_url.startswith("http"):
        # paging "next" URLs already carry the token; fresh paths need it added
        p["access_token"] = META_TOKEN
    for attempt in range(5):
        r = requests.get(url, params=p, timeout=60)
        if r.status_code == 200:
            return r.json()
        try:
            err = (r.json() or {}).get("error", {})
        except ValueError:
            err = {}
        code = err.get("code")
        if code == 190:
            print("ERROR: Meta rejected the access token (code 190: invalid or expired).")
            print("User tokens expire about every 60 days. Generate a System User token")
            print("with ads_read (business.facebook.com > Business settings > Users >")
            print("System users) and update the META_ACCESS_TOKEN secret in Doppler.")
            sys.exit(1)
        retryable = r.status_code == 429 or r.status_code >= 500 or code in (1, 2, 4, 17, 32, 613)
        if retryable and attempt < 4:
            wait = min(60, 10 * (attempt + 1))
            print(f"  Meta {r.status_code} (error code {code}), retrying in {wait}s...")
            time.sleep(wait)
            continue
        print(f"ERROR: Meta API call failed: HTTP {r.status_code} {r.text[:300]}")
        sys.exit(1)
    return {}


def meta_get_all(path, params):
    """Follow Graph API pagination to the end."""
    rows, data = [], meta_get(path, params)
    while True:
        rows.extend(data.get("data", []))
        nxt = (data.get("paging") or {}).get("next")
        if not nxt:
            return rows
        data = meta_get(nxt)


INSIGHT_FIELDS = ",".join([
    "campaign_id", "campaign_name", "adset_id", "adset_name",
    "ad_id", "ad_name", "objective", "impressions", "reach", "frequency",
    "clicks", "inline_link_clicks", "spend", "actions",
])


def fetch_insights(since, until, daily=False):
    """Ad-level insights for a date window. daily=True returns one row per ad
    per day (the stored history); daily=False returns one row per ad for the
    whole window, which is the only way to get a true multi-day frequency
    (reach does not sum across days)."""
    params = {
        "level": "ad",
        "fields": INSIGHT_FIELDS,
        "time_range": json.dumps({"since": since, "until": until}),
        "limit": 200,
    }
    if daily:
        params["time_increment"] = 1
    return meta_get_all(f"{AD_ACCOUNT}/insights", params)


def account_info():
    """Name, currency and status: confirms the token reaches the right account
    before anything else runs, and fails with a clear message if not."""
    d = meta_get(AD_ACCOUNT, {"fields": "name,currency,account_status"})
    status = {1: "active", 2: "disabled", 3: "unsettled"}.get(
        d.get("account_status"), str(d.get("account_status")))
    print(f"Ad account: {d.get('name')} ({d.get('currency')}), status: {status}")
    return d


def ad_statuses():
    """Every ad's effective_status, so recommendations only nag about ads that
    are actually running, and broken ones (disapproved, with issues) get
    called out even when they served nothing."""
    rows = meta_get_all(f"{AD_ACCOUNT}/ads",
                        {"fields": "name,effective_status,updated_time", "limit": 200})
    return {r["id"]: r for r in rows}


# ---------------------------------------------------------------- shaping

def _i(v):
    return int(float(v or 0))


def _f(v):
    return float(v or 0)


def pick_result(actions):
    """The first action type from RESULT_PRIORITY present in the row: what
    this ad is considered to be for."""
    by_type = {a.get("action_type"): _i(a.get("value")) for a in (actions or [])}
    for t in RESULT_PRIORITY:
        if by_type.get(t):
            return t, by_type[t]
    return None, 0


def window_by_ad(rows):
    """One dict per ad for a single-window insights response."""
    out = {}
    for r in rows:
        rtype, rval = pick_result(r.get("actions"))
        out[r["ad_id"]] = {
            "ad_name": r.get("ad_name"),
            "campaign_id": r.get("campaign_id"),
            "campaign_name": r.get("campaign_name"),
            "impressions": _i(r.get("impressions")),
            "reach": _i(r.get("reach")),
            "frequency": _f(r.get("frequency")),
            "clicks": _i(r.get("clicks")),
            "link_clicks": _i(r.get("inline_link_clicks")),
            "spend": _f(r.get("spend")),
            "results": rval,
            "result_type": rtype,
        }
    return out


def by_campaign(ads):
    """Roll ad rows up to campaigns. The campaign's result_type is whichever
    type contributed the most results, so mixed campaigns still read sanely."""
    camps = {}
    for a in ads.values():
        c = camps.setdefault(a["campaign_id"], {
            "name": a["campaign_name"], "spend": 0.0, "impressions": 0,
            "clicks": 0, "results": 0, "types": {}})
        c["spend"] += a["spend"]
        c["impressions"] += a["impressions"]
        c["clicks"] += a["clicks"]
        c["results"] += a["results"]
        if a["result_type"]:
            c["types"][a["result_type"]] = c["types"].get(a["result_type"], 0) + a["results"]
    for c in camps.values():
        c["result_type"] = max(c["types"], key=c["types"].get) if c["types"] else None
        del c["types"]
    return camps


def ctr(row):
    return (row["clicks"] / row["impressions"] * 100) if row["impressions"] else 0.0


def cpr(row):
    return (row["spend"] / row["results"]) if row["results"] else None


def totals(ads):
    t = {"spend": 0.0, "impressions": 0, "clicks": 0, "results": 0}
    for a in ads.values():
        for k in t:
            t[k] += a[k]
    return t


# ---------------------------------------------------------------- storage

def store_daily(rows):
    """Upsert the daily history. The 28-day window overlaps prior runs on
    purpose: late-arriving attribution revises recent days, and upsert makes
    the overlap harmless (same pattern as the giving sync)."""
    batch = []
    for r in rows:
        rtype, rval = pick_result(r.get("actions"))
        batch.append({
            "day": r.get("date_start"),
            "campaign_id": r.get("campaign_id"),
            "campaign_name": r.get("campaign_name"),
            "objective": r.get("objective"),
            "adset_id": r.get("adset_id"),
            "adset_name": r.get("adset_name"),
            "ad_id": r.get("ad_id"),
            "ad_name": r.get("ad_name"),
            "impressions": _i(r.get("impressions")),
            "reach": _i(r.get("reach")),
            "frequency": _f(r.get("frequency")),
            "clicks": _i(r.get("clicks")),
            "link_clicks": _i(r.get("inline_link_clicks")),
            "spend": _f(r.get("spend")),
            "results": rval,
            "result_type": rtype,
            "actions": r.get("actions") or [],
        })
    if DRY_RUN:
        print(f"  DRY RUN: would store {len(batch)} daily row(s); nothing written.")
        return
    for start in range(0, len(batch), 500):
        sb.table("meta_ad_insights").upsert(
            batch[start:start + 500], on_conflict="ad_id,day").execute()
    print(f"  stored {len(batch)} daily row(s) in meta_ad_insights.")


def store_recommendations(recs, run_on):
    if DRY_RUN:
        print(f"  DRY RUN: would store {len(recs)} recommendation(s); nothing written.")
        return
    rows = [{
        "run_on": run_on,
        "level": r["level"],
        "entity_id": r["entity_id"],
        "entity_name": r.get("entity_name"),
        "kind": r["kind"],
        "recommendation": r["recommendation"],
        "metrics": r.get("metrics") or {},
    } for r in recs]
    if rows:
        sb.table("meta_ad_recommendations").upsert(
            rows, on_conflict="run_on,level,entity_id,kind").execute()
    print(f"  stored {len(rows)} recommendation(s) in meta_ad_recommendations.")


# ---------------------------------------------------------------- analysis

def analyze(ads7, adsP, camps7, campsP, statuses):
    """Rule-based flags, each one a plain sentence PD can act on in Ads
    Manager. Thresholds are the constants at the top of the file; adjust them
    there, not here."""
    recs = []
    judged = [a for a in ads7.values() if a["impressions"] >= MIN_IMPRESSIONS_TO_JUDGE]
    med_ctr = statistics.median(ctr(a) for a in judged) if len(judged) >= 3 else None
    active = {aid for aid, s in statuses.items() if s.get("effective_status") == "ACTIVE"}

    for aid, a in ads7.items():
        if aid not in active or a["impressions"] < MIN_IMPRESSIONS_TO_JUDGE:
            continue
        c7 = ctr(a)
        p = adsP.get(aid)
        cP = ctr(p) if p and p["impressions"] >= MIN_IMPRESSIONS_TO_JUDGE // 2 else None
        drop = ((cP - c7) / cP) if cP else 0.0
        if a["frequency"] >= FATIGUE_FREQUENCY and cP and drop >= CTR_DROP_ALERT:
            recs.append({
                "level": "ad", "entity_id": aid, "entity_name": a["ad_name"], "kind": "fatigue",
                "recommendation": (
                    f"Rotate creative on '{a['ad_name']}' ({a['campaign_name']}): the average "
                    f"person has seen it {a['frequency']:.1f} times this week and its click rate "
                    f"fell {drop * 100:.0f}% (from {cP:.2f}% to {c7:.2f}%). Same message, fresh look."),
                "metrics": {"frequency": a["frequency"], "ctr": c7, "prior_ctr": cP}})
        elif c7 < LOW_CTR_FLOOR or (med_ctr and c7 < 0.5 * med_ctr):
            vs = f" against an account median of {med_ctr:.2f}%" if med_ctr else ""
            recs.append({
                "level": "ad", "entity_id": aid, "entity_name": a["ad_name"], "kind": "low_ctr",
                "recommendation": (
                    f"'{a['ad_name']}' ({a['campaign_name']}) is not earning its spot: "
                    f"{c7:.2f}% of viewers click{vs}, with ${a['spend']:,.2f} spent this week. "
                    f"Pause it or try a new hook."),
                "metrics": {"ctr": c7, "median_ctr": med_ctr, "spend": a["spend"]}})

    # The winner: the cheapest cost-per-result ad, when it is meaningfully
    # cheaper than the account average and not already taking most of the spend.
    with_results = [(aid, a) for aid, a in ads7.items()
                    if a["impressions"] >= MIN_IMPRESSIONS_TO_JUDGE
                    and a["results"] >= MIN_RESULTS_TO_COMPARE]
    total = totals(ads7)
    if len(with_results) >= 2 and total["results"]:
        avg = total["spend"] / total["results"]
        aid, best = min(with_results, key=lambda x: cpr(x[1]))
        best_cpr = cpr(best)
        share = (best["spend"] / total["spend"]) if total["spend"] else 0
        if best_cpr is not None and best_cpr <= 0.6 * avg and share < 0.5:
            recs.append({
                "level": "ad", "entity_id": aid, "entity_name": best["ad_name"], "kind": "scale_winner",
                "recommendation": (
                    f"Shift budget toward '{best['ad_name']}' ({best['campaign_name']}): "
                    f"${best_cpr:,.2f} per {best['result_type']} against an account average of "
                    f"${avg:,.2f}, and it only got {share * 100:.0f}% of the week's spend."),
                "metrics": {"cost_per_result": best_cpr, "account_avg": avg, "spend_share": share}})

    for cid, c in camps7.items():
        p = campsP.get(cid)
        if not p or c["results"] < MIN_RESULTS_TO_COMPARE or p["results"] < MIN_RESULTS_TO_COMPARE:
            continue
        now_cpr, was_cpr = c["spend"] / c["results"], p["spend"] / p["results"]
        if was_cpr and now_cpr >= (1 + COST_SPIKE_ALERT) * was_cpr:
            recs.append({
                "level": "campaign", "entity_id": cid, "entity_name": c["name"], "kind": "cost_spike",
                "recommendation": (
                    f"Campaign '{c['name']}': cost per {c['result_type']} rose from "
                    f"${was_cpr:,.2f} to ${now_cpr:,.2f} week over week. Worth a look "
                    f"before it drifts further."),
                "metrics": {"cost_per_result": now_cpr, "prior": was_cpr}})

    for aid, s in statuses.items():
        es = s.get("effective_status")
        name = s.get("name") or aid
        if es in ("DISAPPROVED", "WITH_ISSUES"):
            # Only recent ones: an ad disapproved months ago and left behind
            # should not be re-flagged every week forever.
            try:
                updated = datetime.fromisoformat(s.get("updated_time") or "")
            except ValueError:
                updated = None
            if updated and (datetime.now(timezone.utc) - updated).days > 90:
                continue
            recs.append({
                "level": "ad", "entity_id": aid, "entity_name": name, "kind": "needs_attention",
                "recommendation": (
                    f"'{name}' is {es.replace('_', ' ').lower()}. Fix or replace it in "
                    f"Ads Manager; it reaches nobody while it sits there."),
                "metrics": {"effective_status": es}})
        elif es == "ACTIVE" and (aid not in ads7 or ads7[aid]["impressions"] == 0):
            recs.append({
                "level": "ad", "entity_id": aid, "entity_name": name, "kind": "no_delivery",
                "recommendation": (
                    f"'{name}' is active but served nothing in the last 7 days. If it should "
                    f"be running, check its review status and budget; if it is finished, "
                    f"pause it to keep the account tidy."),
                "metrics": {"effective_status": es}})
    return recs


def render_report(ads7, adsP, camps7, campsP):
    if not ads7:
        return "No delivery in the last 7 days: nothing served, nothing spent."
    t7, tp = totals(ads7), totals(adsP)
    lines = ["Account, last 7 days (vs the 7 before):"]
    lines.append(
        f"  spend ${t7['spend']:,.2f} (prior ${tp['spend']:,.2f}), "
        f"{t7['impressions']:,} impressions (prior {tp['impressions']:,}), "
        f"CTR {ctr(t7):.2f}% (prior {ctr(tp):.2f}%)")
    lines.append("Campaigns:")
    for cid, c in sorted(camps7.items(), key=lambda x: -x[1]["spend"]):
        p = campsP.get(cid)
        line = f"  {c['name']}: ${c['spend']:,.2f}"
        if p:
            line += f" (prior ${p['spend']:,.2f})"
        line += f", {c['impressions']:,} impressions, CTR {ctr(c):.2f}%"
        if c["results"]:
            line += f", {c['results']} {c['result_type']} at ${c['spend'] / c['results']:,.2f} each"
            if p and p["results"]:
                line += f" (prior ${p['spend'] / p['results']:,.2f})"
        lines.append(line)
    return "\n".join(lines)


def strategy_note(report, recs):
    """A short written take on top of the rule-based flags, using the same
    Anthropic key the sermon enrichment uses. Optional: without the key the
    numbers and flags stand on their own."""
    if not ANTHROPIC_API_KEY:
        print("  (no ANTHROPIC_API_KEY: skipping the written strategy note)")
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        flags = "\n".join(f"- {r['recommendation']}" for r in recs) or "- none this week"
        prompt = (
            "You advise a church on its Meta ad account. The ads exist to reach people "
            "not yet part of the house: invitations, sermon clips, event awareness. "
            "Below are this week's numbers and this week's rule-based flags.\n\n"
            f"{report}\n\nFlags:\n{flags}\n\n"
            "Write 3 to 5 short bullets of strategy for the coming week: what to keep, "
            "what to change, what to test next. Plain language, no marketing jargon, "
            "each bullet one concrete action a busy pastor can take in Ads Manager in "
            "under ten minutes. Do not use em dashes. Reply with only the bullets.")
        msg = client.messages.create(
            model=STRATEGY_MODEL, max_tokens=600,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return text or None
    except Exception as e:
        print("  strategy note failed:", repr(e))
        return None


# ---------------------------------------------------------------- main

def main():
    now = datetime.now(timezone.utc)
    print(f"Meta ads report starting ({'DRY RUN' if DRY_RUN else 'live'}), {now:%Y-%m-%d %H:%M} UTC")
    if not (META_TOKEN and AD_ACCOUNT):
        print("Meta ads: not connected yet. To activate:")
        print("  1. Apply supabase/meta_ads_schema.sql in the Supabase SQL editor.")
        print("  2. Add a META_ACCESS_TOKEN secret: a System User token with ads_read")
        print("     (business.facebook.com > Business settings > Users > System users).")
        print("  3. Add a META_AD_ACCOUNT_ID secret: the act= number in the Ads Manager URL.")
        print("Until then this job does nothing, so it is safe to merge and schedule.")
        return

    account_info()

    # Windows end yesterday so every day in them is complete. On the Monday
    # schedule that makes "last 7 days" Monday through Sunday: the full week,
    # including Sunday's push.
    until = (now - timedelta(days=1)).date()
    daily = fetch_insights(str(until - timedelta(days=LOOKBACK_DAYS - 1)), str(until), daily=True)
    print(f"  {len(daily)} daily ad row(s) over the last {LOOKBACK_DAYS} days")
    last7 = fetch_insights(str(until - timedelta(days=6)), str(until))
    prior7 = fetch_insights(str(until - timedelta(days=13)), str(until - timedelta(days=7)))
    statuses = ad_statuses()

    try:
        store_daily(daily)
    except Exception as e:
        print(f"ERROR: could not write to meta_ad_insights ({e}).")
        print("Has supabase/meta_ads_schema.sql been applied to the project?")
        sys.exit(1)

    ads7, adsP = window_by_ad(last7), window_by_ad(prior7)
    camps7, campsP = by_campaign(ads7), by_campaign(adsP)
    report = render_report(ads7, adsP, camps7, campsP)
    print()
    print(report)

    recs = analyze(ads7, adsP, camps7, campsP, statuses)
    print()
    if recs:
        print("Recommendations:")
        for r in recs:
            print(f"  [{r['kind']}] {r['recommendation']}")
    else:
        print("Recommendations: none. Nothing fatigued, nothing off the pace.")

    if ads7:
        note = strategy_note(report, recs)
        if note:
            print()
            print("Strategy note:")
            for ln in note.splitlines():
                print(f"  {ln}")
            recs.append({"level": "account", "entity_id": "account",
                         "entity_name": None, "kind": "strategy",
                         "recommendation": note, "metrics": {}})

    try:
        store_recommendations(recs, str(now.date()))
    except Exception as e:
        print(f"ERROR: could not write to meta_ad_recommendations ({e}).")
        print("Has supabase/meta_ads_schema.sql been applied to the project?")
        sys.exit(1)

    print()
    print(f"Done. {len(recs)} recommendation(s) this run; the Monday digest will show them.")


if __name__ == "__main__":
    main()
