"""
Where the Supabase credentials come from.

The platform is one Supabase project read by two codebases that grew up apart,
so the same two values ended up with four names:

    project URL   NEXT_PUBLIC_SUPABASE_URL  (intranet)   SUPABASE_URL  (here)
    service key   SUPABASE_SERVICE_ROLE_KEY (intranet)   SUPABASE_SERVICE_KEY (here)

Two names for one value means one of them is always the stale copy, and
rotating the key fixes one caller while quietly breaking the other. That is
exactly how the 2026-08-05 run died.

So: accept every name, prefer the intranet's, and let Doppler hold one of each.
"""
import os
import sys

# The project URL ships in every frontend bundle, so it is public, not secret.
# Defaulting to it means a missing or fat-fingered value is a warning rather
# than an outage.
DEFAULT_SUPABASE_URL = "https://eibrykdamgyoylnqknao.supabase.co"

URL_NAMES = ("NEXT_PUBLIC_SUPABASE_URL", "SUPABASE_URL")
KEY_NAMES = ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")


def _first(names):
    """First of these env vars that is set to something."""
    for n in names:
        v = (os.environ.get(n) or "").strip().strip("'\"")
        if v:
            return v, n
    return "", None


def supabase_url():
    raw, name = _first(URL_NAMES)
    u = raw.rstrip("/")
    if u and not u.startswith("http"):
        u = "https://" + u
    if ".supabase.co" not in u:
        if u:
            print(f"WARNING: {name} ({u!r}) is not a Supabase URL; using {DEFAULT_SUPABASE_URL}")
        u = DEFAULT_SUPABASE_URL
    return u


def service_key(required=True):
    """The service_role key, checked for shape.

    A wrong value should name itself at startup, not surface as a 401 from
    whatever query happens to run first.
    """
    key, name = _first(KEY_NAMES)
    if not key:
        if not required:
            return ""
        print(f"ERROR: missing required secret {KEY_NAMES[0]} (or {KEY_NAMES[1]}).")
        print("It is Supabase > project settings > API keys > service_role.")
        print("Never the anon key: it cannot read these tables.")
        sys.exit(1)
    # Service keys are a JWT (eyJ...) or the newer sb_secret_ form. The anon key
    # is a JWT too, so this catches typos and truncation, not key confusion.
    if not (key.startswith("eyJ") or key.startswith("sb_secret_")):
        print(f"ERROR: {name} does not look like a Supabase key (starts with {key[:6]!r}).")
        print("Expected 'eyJ...' or 'sb_secret_...'.")
        sys.exit(1)
    return key
