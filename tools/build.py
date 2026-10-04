#!/usr/bin/env python3
"""Builds JPEG slides + queue.json. Run from the autoposter folder: python3 tools/build.py"""
import glob, json, os, re, sys, textwrap
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(__file__))
import content

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.dirname(ROOT)          # the 50-posts folder
W, H = 1080, 1350
DARK, LIGHT = (20, 38, 46), (231, 238, 225)
CREAM, RED = (240, 238, 228), (176, 58, 40)
SERIF = "/opt/X11/share/system_fonts/Supplemental/PTSerif.ttc"
MONO = "/System/Library/Fonts/SFNSMono.ttf"
NARROW = "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"

def serif(size, bold=False):
    for k in range(4):
        f = ImageFont.truetype(SERIF, size, index=k)
        name = f.getname()[1]
        if bold and "Bold" in name and "Italic" not in name: return f
        if not bold and name == "Regular": return f
    return ImageFont.truetype(SERIF, size)

def mono(size, bold=False):
    f = ImageFont.truetype(MONO, size)
    if bold:
        try: f.set_variation_by_name("Bold")
        except Exception: pass
    return f

def wrap(draw, text, font, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= width: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def chrome(dr, n, dark):
    fg = CREAM if dark else DARK
    sub = (150, 160, 162) if dark else (110, 125, 120)
    x = 88
    for ch in "READBANK":
        dr.text((x, 90), ch, font=mono(28, True), fill=fg); x += 22.5
    dr.text((992, 90), f"{n:02d}/07", font=mono(28, True), fill=sub, anchor="ra")
    for i in range(7):
        col = RED if i == n - 1 else ((70, 85, 90) if dark else (186, 196, 186))
        dr.rectangle((726 + 38 * i, 1266, 756 + 38 * i, 1272), fill=col)
    return sub

def text_block(dr, text, dark, n, hook=False):
    fg = CREAM if dark else DARK
    main, _, src = text.partition("||")
    size = 82 if hook else 72
    while True:
        f = serif(size, bold=hook)
        lines = wrap(dr, main, f, 900)
        lh = int(size * 1.25)
        if len(lines) * lh <= 640 or size <= 40: break
        size -= 4
    total = len(lines) * lh
    top = 690 - total // 2
    if hook: dr.rectangle((88, top - 70, 192, top - 62), fill=RED)
    y = top
    for l in lines:
        dr.text((88, y), l, font=f, fill=fg); y += lh
    if src:
        sf = mono(24)
        for l in wrap(dr, src, sf, 900):
            y += 14; dr.text((88, y + 20), l, font=sf, fill=(150, 160, 162) if dark else (110, 125, 120)); y += 20

def slide(n, text, kind):
    dark = kind in ("hook", "cta")
    im = Image.new("RGB", (W, H), DARK if dark else LIGHT); dr = ImageDraw.Draw(im)
    sub = chrome(dr, n, dark)
    if kind == "cta":
        big = ImageFont.truetype(NARROW, 96)
        dr.text((88, 470), "READING EARNS", font=big, fill=CREAM)
        dr.text((88, 570), "SCREEN TIME.", font=big, fill=CREAM)
        dr.rectangle((88, 430, 192, 438), fill=RED)
        h = 204
        layer = Image.new("RGBA", (920, h), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
        ld.rectangle((8, 8, 912, h - 8), outline=CREAM, width=6)
        ld.text((50, 36), "DOWNLOAD NOW", font=ImageFont.truetype(NARROW, 78), fill=CREAM)
        ld.text((52, h - 78), "Read. Earn screen time.", font=mono(34), fill=CREAM)
        layer = layer.rotate(2.3, resample=Image.BICUBIC, expand=True)
        im.paste(layer, (88 - (layer.width - 920) // 2, 720 - (layer.height - h) // 2), layer)
        dr.text((88, 960), "LINK IN BIO", font=mono(30), fill=sub)
        dr.text((88, 1240), "TAP THE LINK", font=mono(28), fill=sub)
    else:
        text_block(dr, text, dark, n, hook=(kind == "hook"))
        dr.text((88, 1240), "SWIPE →" if kind == "hook" else f"{n:02d}", font=mono(28), fill=sub)
    return im

def save_jpegs(images, post_id):
    out = os.path.join(ROOT, "images", post_id); os.makedirs(out, exist_ok=True)
    paths = []
    for i, im in enumerate(images, 1):
        p = f"images/{post_id}/{i:02d}.jpg"
        im.convert("RGB").save(os.path.join(ROOT, p), "JPEG", quality=92); paths.append(p)
    return paths

CTA = {"A": "Does this sound like your house? Tell me in the comments.", "F": "Does this sound like your house? Tell me in the comments.",
       "B": "Agree or disagree? Comment below.", "C": "Save this and send it to another parent.", "D": "Save this for later.",
       "E": "Drop your favorite book in the comments.", "G": "Save this for later."}

# Original slides with a dash in the text, re-rendered without it.
NODASH = {
    "A08": {6: "But it can beat it on price, if reading is how you buy the tablet."},
    "E34": {2: "Inference: reading what happens between panels.", 3: "Visual literacy: pacing, framing, tone."},
    "E38": {2: "Goosebumps: the original gateway drug", 4: "Small Spaces by Katherine Arden", 5: "Coraline by Neil Gaiman"},
}

def existing_caption(pid):
    t = open(glob.glob(os.path.join(SRC, pid + "-*/caption.txt"))[0]).read().strip().split("\n")
    body = []
    for l in t:
        if l.startswith("Join the waitlist"): break
        body.append(l)
    body = "\n".join(body).strip().replace("*", "")
    tags = [l for l in t if l.startswith("#")][-1]
    extra = "" if "omment" in body else "\n\n" + CTA[pid[0]]
    return f"{body}{extra}\n\nDownload ReadBank, link in bio 📚\n\n{tags}"

def build():
    pools = {k: [] for k in ("ex", "q", "founder", "pick", "sat", "res", "books")}
    # existing carousels (07.png already says DOWNLOAD NOW). E38 is Halloween, keep it early.
    ex = "B11 C20 D25 A08 B13 E38 E34 D27 C21 B12 A07 D26 E35 B14 C22 D28 B16 G49 D29 F42 E37 F43 D30".split()
    for pid in ex:
        d = glob.glob(os.path.join(SRC, pid + "-*"))[0]
        ims = [Image.open(os.path.join(d, f"{i:02d}.png")) for i in range(1, 8)]
        for n, t in NODASH.get(pid, {}).items():
            ims[n - 1] = slide(n, t, "body")
        paths = save_jpegs(ims, os.path.basename(d))
        item = {"id": os.path.basename(d), "type": "carousel", "images": paths, "caption": existing_caption(pid)}
        if pid == "E38": item["not_after"] = "2026-11-01"
        pools["ex"].append(item)
    for f in sorted(glob.glob(os.path.join(SRC, "question-cards/*.png"))):
        date = os.path.basename(f)[:-4]
        q = {"2026-10-08": "What is the one screen time rule you have given up on? Be honest.",
             "2026-10-15": "Did you ever fudge a reading log as a kid? Comment YES.",
             "2026-10-22": "How many hours of screen time does your kid get on a normal school day? Just drop a number.",
             "2026-10-29": "Would you rather your kid earn screen time by reading, or get a fixed daily limit? Comment A or B.",
             "2026-11-05": "What is the one book your kid actually finished? Drop it below.",
             "2026-11-12": "What is harder at bedtime: putting the screen down or picking up a book? Comment SCREEN or BOOK."}[date]
        paths = save_jpegs([Image.open(f)], f"q-{date}")
        pools["q"].append({"id": f"q-{date}", "type": "single", "images": paths,
                           "caption": f"{q}\n\nDownload ReadBank, link in bio 📚\n\n#parenting #screentime #raisingreaders #parentingtips #momlife"})
    for pid, kind, hook, body, lead in content.POSTS:
        ims = [slide(1, hook, "hook")] + [slide(i + 2, t, "body") for i, t in enumerate(body)] + [slide(7, "", "cta")]
        paths = save_jpegs(ims, pid)
        pools[kind].append({"id": pid, "type": "carousel", "images": paths,
                            "caption": f"{lead}\n\nDownload ReadBank, link in bio 📚\n\n{content.TAGS[kind]}"})
    total = {k: len(v) for k, v in pools.items()}
    queue, last = [pools["founder"].pop(0)], "founder"
    while any(pools.values()):
        k = max((k for k in pools if pools[k] and k != last), key=lambda k: len(pools[k]) / total[k], default=None)
        if k is None: k = next(k for k in pools if pools[k])
        queue.append(pools[k].pop(0)); last = k
    json.dump(queue, open(os.path.join(ROOT, "queue.json"), "w"), indent=2, ensure_ascii=False)
    if not os.path.exists(os.path.join(ROOT, "posted.json")):
        json.dump({}, open(os.path.join(ROOT, "posted.json"), "w"))
    print(len(queue), "posts queued")

if __name__ == "__main__":
    build()
