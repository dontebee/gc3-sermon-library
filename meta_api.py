"""The Meta Graph API client shared by the ads jobs.

One token, one ad account, one retry policy. meta_ads_report.py (the weekly
scoreboard) and meta_ads_history.py (the era diagnostic) both speak through
this module, so a Graph API quirk gets fixed once, not twice.

Env vars:
  META_ACCESS_TOKEN   Marketing API token with ads_read. Use a System User
                      token (business.facebook.com > Business settings >
                      Users > System users): user tokens expire about every
                      60 days, system user tokens do not.
  META_AD_ACCOUNT_ID  the ad account id, with or without the act_ prefix
                      (it is the act=... number in the Ads Manager URL)
"""
import os
import sys
import time

import requests

META_API_VERSION = "v23.0"
GRAPH = f"https://graph.facebook.com/{META_API_VERSION}"

META_TOKEN = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
_raw_acct = (os.environ.get("META_AD_ACCOUNT_ID") or "").strip()
AD_ACCOUNT = _raw_acct if _raw_acct.startswith("act_") else (f"act_{_raw_acct}" if _raw_acct else "")


def connected():
    """Both secrets present. Callers print their own setup instructions."""
    return bool(META_TOKEN and AD_ACCOUNT)


def meta_get(path_or_url, params=None, fatal=True):
    """GET from the Graph API with retry on throttling and server errors.

    Meta signals throttling as HTTP 400 with error codes 4, 17 or 32 rather
    than a clean 429, so the retry decision reads the error body, not just the
    status line. Code 190 is an invalid or expired token, which retrying will
    never fix, so it gets an explanation and a hard stop instead.

    A caller may pass its own access_token in params (the lead mirror uses
    per-page tokens); otherwise the system user token is used. fatal=False
    returns None on a non-retryable failure instead of exiting, for jobs that
    should degrade politely while permissions are still being set up.
    """
    url = path_or_url if path_or_url.startswith("http") else f"{GRAPH}/{path_or_url}"
    p = dict(params or {})
    if not path_or_url.startswith("http"):
        # paging "next" URLs already carry the token; fresh paths need one added
        p.setdefault("access_token", META_TOKEN)
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
            if fatal:
                sys.exit(1)
            return None
        retryable = r.status_code == 429 or r.status_code >= 500 or code in (1, 2, 4, 17, 32, 613)
        if retryable and attempt < 4:
            wait = min(60, 10 * (attempt + 1))
            print(f"  Meta {r.status_code} (error code {code}), retrying in {wait}s...")
            time.sleep(wait)
            continue
        print(f"ERROR: Meta API call failed: HTTP {r.status_code} {r.text[:300]}")
        if fatal:
            sys.exit(1)
        return None
    return {}


def meta_get_all(path, params, fatal=True):
    """Follow Graph API pagination to the end. With fatal=False a failure on
    any page returns None (not a partial list), so callers can tell a broken
    call from an empty result."""
    rows, data = [], meta_get(path, params, fatal=fatal)
    if data is None:
        return None
    while True:
        rows.extend(data.get("data", []))
        nxt = (data.get("paging") or {}).get("next")
        if not nxt:
            return rows
        data = meta_get(nxt, fatal=fatal)
        if data is None:
            return None


def account_info():
    """Name, currency and status: confirms the token reaches the right account
    before anything else runs, and fails with a clear message if not."""
    d = meta_get(AD_ACCOUNT, {"fields": "name,currency,account_status"})
    status = {1: "active", 2: "disabled", 3: "unsettled"}.get(
        d.get("account_status"), str(d.get("account_status")))
    print(f"Ad account: {d.get('name')} ({d.get('currency')}), status: {status}")
    return d
