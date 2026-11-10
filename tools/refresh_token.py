#!/usr/bin/env python3
"""Makes a Facebook Page token that does NOT expire and saves it as the META_PAGE_TOKEN secret. Run it yourself:

    python3 tools/refresh_token.py

You will be asked for three things (typed or pasted, nothing is shown on screen and nothing is saved on disk):
  1. App secret   developers.facebook.com > My Apps > ReadBank Poster > App settings > Basic > App secret > Show
  2. A short-lived user token   developers.facebook.com/tools/explorer > pick "ReadBank Poster" > Generate Access Token with these permissions:
     pages_show_list, pages_read_engagement, pages_manage_posts, instagram_basic, instagram_content_publish, business_management
  (the Page ID and App ID are filled in for you)
It then trades the short token for a long one, asks Meta for the Page token (which never expires), checks it, and stores it with `gh secret set`.
"""
import getpass, json, subprocess, sys, urllib.error, urllib.parse, urllib.request

APP_ID = "1109398195115030"
PAGE_ID = "1266021983260107"
REPO = "e10than/readbank-autoposter"
G = "https://graph.facebook.com/v25.0"


def get(path, **p):
    try:
        with urllib.request.urlopen(f"{G}/{path}?" + urllib.parse.urlencode(p), timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Meta said no: {e.read().decode()}")


def main():
    secret = getpass.getpass("App secret: ").strip()
    short = getpass.getpass("Short-lived user token from the Graph API Explorer: ").strip()
    if not secret or not short:
        sys.exit("Both are needed.")
    long_ = get("oauth/access_token", grant_type="fb_exchange_token", client_id=APP_ID, client_secret=secret, fb_exchange_token=short)["access_token"]
    page_tok = None
    for p in get("me/accounts", access_token=long_, limit=100).get("data", []):
        if p["id"] == PAGE_ID:
            page_tok = p["access_token"]
    if not page_tok:
        page_tok = get(PAGE_ID, fields="access_token", access_token=long_).get("access_token")
    if not page_tok:
        sys.exit("Could not get the Page token. Make sure you tick the ReadBank Page when Facebook asks which Pages to allow.")
    d = get("debug_token", input_token=page_tok, access_token=f"{APP_ID}|{secret}").get("data", {})
    scopes = set(d.get("scopes", []))
    print("Token valid:", d.get("is_valid"), "| expires_at:", d.get("expires_at"), "(0 means it never expires)")
    missing = [s for s in ("instagram_content_publish", "pages_manage_posts") if s not in scopes]
    if not d.get("is_valid") or missing:
        sys.exit(f"Not saving this token. Valid={d.get('is_valid')}, missing permissions: {missing}")
    r = subprocess.run(["gh", "secret", "set", "META_PAGE_TOKEN", "--repo", REPO], input=page_tok.encode(), capture_output=True)
    if r.returncode:
        sys.exit("Could not save the secret: " + r.stderr.decode())
    print("Saved META_PAGE_TOKEN to", REPO, ". Next: gh workflow run 'Daily post' --repo", REPO, "-f mode=check")


if __name__ == "__main__":
    main()
