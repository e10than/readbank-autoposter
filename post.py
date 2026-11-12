#!/usr/bin/env python3
"""Posts the next video in queue.json to Instagram (Reel) and Facebook (video). Standard library only.

  python3 post.py            post the next video (what the schedule runs)
  python3 post.py --check    check the token, the Instagram and Facebook accounts, and every queued video. Posts nothing.
  python3 post.py --dry      show what would be posted. Posts nothing.

Env: META_PAGE_TOKEN, FB_PAGE_ID, IG_USER_ID, VIDEO_BASE_URL   (optional: GRAPH_VERSION, FORCE=1)
Each run posts ONE video, then stops. Progress is saved per platform, so a retry never double-posts.
"""
import datetime, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH = "https://graph.facebook.com/" + os.environ.get("GRAPH_VERSION", "v25.0")
TOKEN = os.environ.get("META_PAGE_TOKEN", "").strip()
PAGE = os.environ.get("FB_PAGE_ID", "").strip()
IG = os.environ.get("IG_USER_ID", "").strip()
BASE = os.environ.get("VIDEO_BASE_URL", "").rstrip("/")
TODAY = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
HASHTAGS = "#screentime #parenting #reading #readbank"
TOKEN_HELP = ("The Meta token is missing, expired or revoked. Fix: on your computer run  python3 tools/refresh_token.py  "
              "(it makes a token that does not expire and saves it as the META_PAGE_TOKEN secret for you).")


class Fail(Exception):
    pass


def call(method, path, params=None, token=None, retries=3):
    params = dict(params or {})
    params["access_token"] = token or TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = f"{GRAPH}/{path}"
    last = None
    for attempt in range(retries):
        try:
            if method == "GET":
                req = urllib.request.Request(url + "?" + data.decode())
            else:
                req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                err = json.loads(body).get("error", {})
            except Exception:
                err = {}
            if err.get("code") == 190 or err.get("type") == "OAuthException" and err.get("code") in (102, 190):
                raise Fail(f"{TOKEN_HELP}\n(Meta said: {err.get('message')})")
            retriable = e.code >= 500 or err.get("is_transient") or err.get("code") in (1, 2, 4, 17, 32, 341)
            last = f"Meta API error on {method} {path}: {body}"
            if not retriable:
                raise Fail(last)
        except (urllib.error.URLError, TimeoutError) as e:
            last = f"Network error on {method} {path}: {e}"
        time.sleep(5 * (attempt + 1))
    raise Fail(last)


def head(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.headers.get("Content-Type", ""), int(r.headers.get("Content-Length") or 0)


def page_token():
    """Facebook needs the Page's own token. If the stored token is a user token, Meta hands back the Page token."""
    try:
        return call("GET", PAGE, {"fields": "access_token"}).get("access_token") or TOKEN
    except Fail:
        return TOKEN


def caption_of(item):
    return item["caption"].strip() + "\n\n" + HASHTAGS


def post_instagram(item, url):
    c = call("POST", f"{IG}/media", {"media_type": "REELS", "video_url": url, "caption": caption_of(item), "share_to_feed": "true"})["id"]
    last = ""
    for _ in range(90):                                   # up to 6 minutes of processing
        info = call("GET", c, {"fields": "status_code,status"})
        last = info.get("status_code")
        if last == "FINISHED":
            break
        if last in ("ERROR", "EXPIRED"):
            raise Fail(f"Instagram could not process the video ({last}): {info.get('status')}")
        time.sleep(4)
    else:
        raise Fail(f"Instagram was still processing after 6 minutes (last status {last}).")
    media = call("POST", f"{IG}/media_publish", {"creation_id": c})["id"]
    try:
        return media, call("GET", media, {"fields": "permalink"}).get("permalink", "")
    except Fail:
        return media, ""


def post_facebook(item, url):
    r = call("POST", f"{PAGE}/videos", {"file_url": url, "description": caption_of(item), "published": "true"}, page_token())
    return r["id"]


def read_state():
    p = os.path.join(HERE, "posted.json")
    return p, (json.load(open(p)) if os.path.exists(p) else {})


def save(p, state):
    json.dump(state, open(p, "w"), indent=2)


def video_url(item):
    return f"{BASE}/{item['video']}"


def check(queue, state):
    """Everything that could stop a post, found before it matters. Returns True if all good."""
    ok = True

    def line(good, text):
        nonlocal ok
        ok = ok and good
        print(("OK   " if good else "FAIL ") + text)
    if not all((TOKEN, PAGE, IG, BASE)):
        line(False, "Missing META_PAGE_TOKEN, FB_PAGE_ID, IG_USER_ID or VIDEO_BASE_URL")
        return False
    try:
        me = call("GET", PAGE, {"fields": "name,access_token"}, retries=1)
        line(True, f"Facebook Page reachable: {me.get('name')}")
    except Fail as e:
        line(False, f"Facebook Page: {e}")
        return False
    try:
        ig = call("GET", IG, {"fields": "username"}, retries=1)
        line(True, f"Instagram account reachable: @{ig.get('username')}")
    except Fail as e:
        line(False, f"Instagram account: {e}")
    try:                                                    # does the token expire soon?
        d = call("GET", "debug_token", {"input_token": TOKEN}, retries=1).get("data", {})
        exp = d.get("expires_at", 0)
        if exp:
            days = (datetime.datetime.fromtimestamp(exp) - datetime.datetime.now()).days
            line(days > 7, f"Token expires in {days} days" + ("" if days > 7 else ". " + TOKEN_HELP))
        else:
            line(True, "Token does not expire")
        scopes = set(d.get("scopes", []))
        for need in ("instagram_content_publish", "pages_manage_posts"):
            if scopes and need not in scopes:
                line(False, f"Token is missing the permission {need}")
    except Fail as e:
        print("note  could not read token details:", str(e)[:140])
    try:
        lim = call("GET", f"{IG}/content_publishing_limit", {"fields": "quota_usage,config"}, retries=1)
        print("info  Instagram publishing quota:", json.dumps(lim.get("data", lim)))
    except Fail:
        pass
    pending = [i for i in queue if not (state.get(i["id"], {}).get("ig") and state.get(i["id"], {}).get("fb")) and not state.get(i["id"], {}).get("skipped")]
    print(f"info  {len(pending)} videos left in the queue")
    for item in pending[:3]:                                # the next few must be reachable by Meta
        u = video_url(item)
        try:
            status, ctype, size = head(u)
            good = status == 200 and size > 10000
            line(good, f"{item['id']}: public link works ({ctype}, {size // 1024} KB)")
        except Exception as e:
            line(False, f"{item['id']}: public link failed: {e}")
    return ok


def main():
    queue = json.load(open(os.path.join(HERE, "queue.json")))
    sp, state = read_state()
    args = sys.argv[1:]
    if "--check" in args:
        sys.exit(0 if check(queue, state) else 1)
    dry = "--dry" in args
    if not dry and not all((TOKEN, PAGE, IG, BASE)):
        raise Fail("Missing META_PAGE_TOKEN, FB_PAGE_ID, IG_USER_ID or VIDEO_BASE_URL")
    done_today = [k for k, v in state.items() if v.get("date") == TODAY and v.get("ig") and v.get("fb")]
    if done_today and os.environ.get("FORCE") != "1":
        print("Already posted today:", done_today)
        return
    # GitHub sometimes starts scheduled runs hours late. A post at midnight is worse than no post, so scheduled runs
    # only post between 3 PM and 10 PM Pacific, Monday to Friday. Manual runs (workflow_dispatch) and FORCE=1 can post any time.
    now_pt = datetime.datetime.now(ZoneInfo("America/Los_Angeles"))
    if not dry and os.environ.get("GITHUB_EVENT_NAME") == "schedule" and os.environ.get("FORCE") != "1" and not (15 <= now_pt.hour < 22 and now_pt.weekday() < 5):
        print(f"Skipping: GitHub started this scheduled run at {now_pt:%H:%M} Pacific, outside the 3 PM to 10 PM weekday posting window. The next scheduled run will post instead.")
        return
    for item in queue:
        s = state.get(item["id"], {})
        if (s.get("ig") and s.get("fb")) or s.get("skipped"):
            continue
        path = os.path.join(HERE, item["video"])
        if not os.path.exists(path):
            raise Fail(f"Video file missing: {item['video']}")
        url = video_url(item)
        print(("DRY RUN: would post " if dry else "Posting ") + item["id"], f"({os.path.getsize(path) // 1024} KB)")
        if dry:
            print(caption_of(item))
            return
        status, ctype, size = head(url)                     # Meta must be able to fetch it
        if status != 200 or size < 10000:
            raise Fail(f"The public link for {item['id']} does not work yet ({status}, {size} bytes): {url}")
        s["date"] = TODAY
        if not s.get("ig"):
            s["ig"], s["permalink"] = post_instagram(item, url)
            state[item["id"]] = s
            save(sp, state)
            print("Instagram done:", s.get("permalink") or s["ig"])
        if not s.get("fb"):
            try:
                s["fb"] = post_facebook(item, url)
            except Fail as e:
                state[item["id"]] = s
                save(sp, state)
                raise Fail(f"Instagram worked but Facebook failed (will retry next run): {e}")
            state[item["id"]] = s
            save(sp, state)
            print("Facebook done:", s["fb"])
        return
    print("Queue is empty. Time to build the next batch.")


if __name__ == "__main__":
    try:
        main()
    except Fail as e:
        print("ERROR:", e)
        sys.exit(1)
