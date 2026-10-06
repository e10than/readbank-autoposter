#!/usr/bin/env python3
"""Posts the next item in queue.json to Instagram and Facebook. Standard library only.

Env: META_PAGE_TOKEN, FB_PAGE_ID, IG_USER_ID, IMAGE_BASE_URL
Optional: GRAPH_VERSION (default v25.0), DRY_RUN=1, FORCE=1 (allow a second post the same day)
Each run posts ONE item, then stops. Nothing runs on its own.
"""
import datetime, json, os, time, urllib.error, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
DRY = os.environ.get("DRY_RUN") == "1"
GRAPH = "https://graph.facebook.com/" + os.environ.get("GRAPH_VERSION", "v25.0")
TOKEN = os.environ.get("META_PAGE_TOKEN", "")
PAGE = os.environ.get("FB_PAGE_ID", "")
IG = os.environ.get("IG_USER_ID", "")
BASE = os.environ.get("IMAGE_BASE_URL", "").rstrip("/")
TODAY = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()


def call(method, path, params, token=None):
    params = dict(params)
    params["access_token"] = token or TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = f"{GRAPH}/{path}"
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode(), method="GET")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Meta API error on {method} {path}: {e.read().decode()}")


def wait_ready(container):
    for _ in range(30):
        s = call("GET", container, {"fields": "status_code"}).get("status_code")
        if s == "FINISHED":
            return
        if s in ("ERROR", "EXPIRED"):
            raise SystemExit(f"Instagram container {container} status {s}")
        time.sleep(4)
    raise SystemExit("Instagram container never finished processing")


def post_instagram(item, urls):
    if len(urls) == 1:
        c = call("POST", f"{IG}/media", {"image_url": urls[0], "caption": item["caption"]})["id"]
    else:
        kids = [call("POST", f"{IG}/media", {"image_url": u, "is_carousel_item": "true"})["id"] for u in urls]
        for k in kids:
            wait_ready(k)
        c = call("POST", f"{IG}/media", {"media_type": "CAROUSEL", "children": ",".join(kids),
                                         "caption": item["caption"]})["id"]
    wait_ready(c)
    return call("POST", f"{IG}/media_publish", {"creation_id": c})["id"]


def page_token():
    """Facebook posts need the Page's own token. If TOKEN is a user token, Meta hands back the Page token."""
    try:
        return call("GET", PAGE, {"fields": "access_token"}).get("access_token") or TOKEN
    except SystemExit:
        return TOKEN


def post_facebook(item, urls):
    pt = page_token()
    if len(urls) == 1:
        return call("POST", f"{PAGE}/photos", {"url": urls[0], "caption": item["caption"]}, pt)["id"]
    ids = [call("POST", f"{PAGE}/photos", {"url": u, "published": "false"}, pt)["id"] for u in urls]
    params = {"message": item["caption"]}
    for i, pid in enumerate(ids):
        params[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
    return call("POST", f"{PAGE}/feed", params, pt)["id"]


def save(state_path, state):
    json.dump(state, open(state_path, "w"), indent=2)


def main():
    queue = json.load(open(os.path.join(HERE, "queue.json")))
    state_path = os.path.join(HERE, "posted.json")
    state = json.load(open(state_path))
    if not DRY and not all((TOKEN, PAGE, IG, BASE)):
        raise SystemExit("Missing META_PAGE_TOKEN, FB_PAGE_ID, IG_USER_ID or IMAGE_BASE_URL")
    done_today = [k for k, v in state.items() if v.get("date") == TODAY and v.get("ig") and v.get("fb")]
    if done_today and os.environ.get("FORCE") != "1":
        print("Already posted today:", done_today)
        return
    for item in queue:
        s = state.get(item["id"], {})
        if (s.get("ig") and s.get("fb")) or s.get("skipped"):
            continue
        if item.get("not_after") and TODAY > item["not_after"]:
            state[item["id"]] = {"skipped": f"past {item['not_after']}"}
            print("Skipping (out of season):", item["id"])
            continue
        urls = [f"{BASE}/{p}" for p in item["images"]]
        print(("DRY RUN: would post " if DRY else "Posting ") + item["id"], f"({len(urls)} images)")
        if DRY:
            print(item["caption"])
            return
        s["date"] = TODAY
        if not s.get("ig"):
            s["ig"] = post_instagram(item, urls)
            state[item["id"]] = s
            save(state_path, state)
        if not s.get("fb"):
            s["fb"] = post_facebook(item, urls)
            state[item["id"]] = s
            save(state_path, state)
        print("Done:", s)
        return
    save(state_path, state)
    print("Queue is empty. Time to build the next batch.")


if __name__ == "__main__":
    main()
