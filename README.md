# ReadBank autoposter

`queue.json` holds the next 60 daily posts (images in `images/`). `post.py` publishes the next unposted item
to Instagram and Facebook, one item per run, and records it in `posted.json`.

## One-time setup (you do this, never paste tokens into chat)
1. Put this folder in a **public** GitHub repo (Instagram needs public image links; the images are served from
   `https://raw.githubusercontent.com/<you>/<repo>/main/images/...`).
2. At developers.facebook.com create an app (type Business). Add the Instagram and Pages permissions:
   `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish`.
   While the app is in development mode it works for your own Page and Instagram with no review.
3. In Graph API Explorer generate a Page access token for the ReadBank Page, then extend it to a long-lived one.
4. Get your Instagram account id: `GET /<page-id>?fields=instagram_business_account`.
5. Set these in your shell (or as GitHub secrets): `META_PAGE_TOKEN`, `FB_PAGE_ID`, `IG_USER_ID`, `IMAGE_BASE_URL`.

## Try it safely
```
DRY_RUN=1 python3 post.py     # prints what it would post, calls nothing
python3 post.py               # posts the next item for real
```

## Notes
- It posts at most one item per day unless `FORCE=1`.
- Holiday items have `not_after` dates and are skipped automatically when out of season.
- Running it on a daily schedule is a separate step that needs your explicit go-ahead.
- Reels are not handled (they need video). Post those from the app.
- Meta uses Graph API v25.0 by default; change `GRAPH_VERSION` when it expires.
