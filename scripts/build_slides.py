#!/usr/bin/env python3
"""Build slide pages and captions from carousel content files.

For every drafts/<id>/carousel.json this writes:
  drafts/<id>/slides/01.html ... 07.html   (rendered to JPEG by render.py)
  drafts/<id>/caption.txt

A carousel.json looks like this:

{
  "type": "useful",                  "useful" or "promo"
  "label": "AFFECTION",              small caps label on every slide
  "cover": {"headline": "5 small ways to *feel close again*", "sub": "..."},
  "points": [                         5 for useful, 4 for promo
    {"heading": "...", "body": "...", "panel_label": "TRY SAYING", "panel": "..."}
  ],
  "resource": {"name": "...", "covers": "..."},     promo only
  "close": {"save": "Save this for ...", "safety": true},
  "caption": "...",
  "hashtags": ["#marriage", "..."]
}

Words wrapped in *asterisks* in the cover headline are shown in deep rose.
Usage: python3 scripts/build_slides.py [carousel-id ...]
"""

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "drafts"

CREAM, BLUSH, INK, MUTED = "#FFFAF6", "#F8EEE7", "#263437", "#5A6767"
ROSE, DEEP, AMBER, WHITE = "#C96D72", "#A95058", "#FDB94A", "#FFFFFF"
SERIF = "'Playfair Display', Georgia, serif"
SANS = "'DM Sans', system-ui, sans-serif"
HANDLE = "@spotseason"
ANCHOR = "You do not have to figure it out alone."
DISCLOSURE = (
    "Affiliate link in bio: I may earn a commission if you buy through it, "
    "at no extra cost to you."
)
SAFETY = (
    "These ideas are for everyday distance and disagreement. If you feel unsafe "
    "or afraid at home, please reach out to qualified local support."
)

PETAL = (
    "M0 0C-12 -10 -19 -22 -11 -32C-6 -38 0 -34 0 -28"
    "C0 -34 6 -38 11 -32C19 -22 12 -10 0 0Z"
)


class BuildError(Exception):
    pass


def esc(text):
    return html.escape(str(text), quote=False)


def emph(text, color):
    return re.sub(
        r"\*(.+?)\*", rf'<span style="color: {color}">\1</span>', esc(text)
    )


def flower(ring=True):
    stroke = ' stroke="#EADED7" stroke-width="2"' if ring else ""
    petals = "".join(
        f'<path d="{PETAL}" transform="rotate({a}) translate(0 -9)"></path>'
        for a in range(0, 360, 60)
    )
    return (
        '<svg width="64" height="64" viewBox="-52 -52 104 104">'
        f'<circle r="50" fill="#FFFFFF"{stroke}></circle>'
        f'<g fill="{AMBER}">{petals}</g><circle r="9" fill="#9BE15D"></circle></svg>'
    )


def arrow(color):
    return (
        f'<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 12h16"></path><path d="M14 6l6 6-6 6"></path></svg>'
    )


def icon(kind):
    paths = {
        "save": '<path d="M6 3h12v18l-6-4.5L6 21z"></path>',
        "follow": '<path d="M12 5v14"></path><path d="M5 12h14"></path>',
        "link": (
            '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"></path>'
            '<path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"></path>'
        ),
    }[kind]
    return (
        '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'style="flex-shrink: 0">{paths}</svg>'
    )


def circle(color, opacity, size, position):
    return (
        f'<div style="position: absolute; width: {size}px; height: {size}px; '
        f'border-radius: 50%; background: {color}; opacity: {opacity}; {position}"></div>'
    )


def frame(n, total, label, background, text, decor, body, footer_right, dark=False):
    label_color = WHITE if dark else DEEP
    count_color = WHITE if dark else MUTED
    return f"""<!doctype html>
<html lang="en-US">
<head>
<meta charset="utf-8">
<title>Slide {n}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Playfair+Display:wght@700&display=block">
<style>html,body{{margin:0;padding:0;background:{background}}}</style>
</head>
<body>
<div style="position: relative; width: 1080px; height: 1350px; box-sizing: border-box; padding: 96px; background: {background}; color: {text}; font-family: {SANS}; font-variant-numeric: lining-nums; display: flex; flex-direction: column; overflow: hidden">
{decor}
<div style="position: relative; display: flex; justify-content: space-between; align-items: center">
<div style="font-size: 30px; font-weight: 700; letter-spacing: 5px; color: {label_color}">{esc(label)}</div>
<div style="font-size: 30px; font-weight: 500; color: {count_color}">{n} / {total}</div>
</div>
<div style="position: relative; flex-grow: 1; display: flex; flex-direction: column; justify-content: center; gap: 36px">
{body}
</div>
<div style="position: relative; display: flex; justify-content: space-between; align-items: center">
<div style="display: flex; align-items: center; gap: 18px">{flower(ring=not dark)}<div style="font-size: 34px; font-weight: 700">{HANDLE}</div></div>
{footer_right}
</div>
</div>
</body>
</html>
"""


def cover_slide(c, total):
    headline = c["cover"]["headline"]
    plain = headline.replace("*", "")
    size = 112 if len(plain) <= 40 else 96 if len(plain) <= 58 else 84
    body = (
        f'<h1 style="margin: 0; font-family: {SERIF}; font-weight: 700; font-size: {size}px; '
        f'line-height: 1.08; letter-spacing: -1px">{emph(headline, DEEP)}</h1>'
        f'<p style="margin: 0; font-size: 44px; line-height: 1.35; color: {MUTED}; '
        f'max-width: 780px">{esc(c["cover"]["sub"])}</p>'
    )
    decor = circle(ROSE, 0.2, 620, "right: -180px; top: -160px") + circle(
        AMBER, 0.28, 300, "left: -120px; bottom: 30px"
    )
    swipe = (
        f'<div style="display: flex; align-items: center; gap: 14px; font-size: 34px; '
        f'font-weight: 700; color: {DEEP}"><span>Swipe</span>{arrow(DEEP)}</div>'
    )
    return frame(1, total, c["label"], CREAM, INK, decor, body, swipe)


def point_slide(c, index, total):
    p = c["points"][index]
    n = index + 2
    blush = index % 2 == 0
    background, panel_bg = (BLUSH, WHITE) if blush else (CREAM, BLUSH)
    decor = (
        circle(ROSE, 0.16, 460, "right: -200px; top: 180px")
        if blush
        else circle(AMBER, 0.26, 460, "left: -170px; bottom: 60px")
    )
    heading = p["heading"]
    h_size = 84 if len(heading) <= 24 else 76 if len(heading) <= 40 else 66
    b_size = 44 if len(p["body"]) <= 125 else 40
    long_slide = len(heading) > 24 and len(p["body"]) > 100
    num_size = 150 if long_slide else 200
    parts = [
        f'<div style="font-family: {SERIF}; font-weight: 700; font-size: {num_size}px; '
        f'line-height: 0.9; color: {ROSE}">{index + 1}</div>',
        f'<h2 style="margin: 0; font-family: {SERIF}; font-weight: 700; font-size: {h_size}px; '
        f'line-height: 1.1">{esc(heading)}</h2>',
        f'<p style="margin: 0; font-size: {b_size}px; line-height: 1.4">{esc(p["body"])}</p>',
    ]
    if p.get("panel"):
        q_size = 46 if len(p["panel"]) <= 72 else 40
        parts.append(
            f'<div style="margin-top: 12px; background: {panel_bg}; border-radius: 28px; '
            'padding: 40px 44px; display: flex; flex-direction: column; gap: 14px">'
            f'<div style="font-size: 26px; font-weight: 700; letter-spacing: 4px; color: {DEEP}">'
            f'{esc(p.get("panel_label", "TRY SAYING"))}</div>'
            f'<div style="font-family: {SERIF}; font-weight: 700; font-size: {q_size}px; '
            f'line-height: 1.3">{esc(p["panel"])}</div></div>'
        )
    return frame(n, total, c["label"], background, INK, decor, "\n".join(parts), arrow(DEEP))


def resource_slide(c, n, total):
    r = c["resource"]
    body = (
        f'<div style="font-size: 30px; font-weight: 700; letter-spacing: 5px; color: {DEEP}">'
        "A RESOURCE FOR THIS</div>"
        f'<h2 style="margin: 0; font-family: {SERIF}; font-weight: 700; font-size: 84px; '
        f'line-height: 1.1">{esc(r["name"])}</h2>'
        f'<p style="margin: 0; font-size: 44px; line-height: 1.4">{esc(r["covers"])}</p>'
        f'<p style="margin: 0; font-size: 36px; line-height: 1.4; color: {MUTED}">'
        "It’s a self-help program, not professional counseling. Results vary.</p>"
        f'<div style="margin-top: 12px; background: {WHITE}; border-radius: 28px; '
        'padding: 40px 44px; display: flex; flex-direction: column; gap: 14px">'
        f'<div style="font-family: {SERIF}; font-weight: 700; font-size: 46px; line-height: 1.3">'
        "Find it at the link in bio.</div>"
        f'<div style="font-size: 30px; line-height: 1.4; color: {MUTED}">'
        "Affiliate link: I may earn a commission if you buy through it, "
        "at no extra cost to you.</div></div>"
    )
    decor = circle(ROSE, 0.16, 460, "right: -200px; top: 180px")
    return frame(n, total, c["label"], BLUSH, INK, decor, body, arrow(DEEP))


def close_slide(c, total):
    close = c.get("close", {})

    def row(kind, strong, rest):
        return (
            '<div style="display: flex; align-items: center; gap: 22px; font-size: 44px; '
            f'line-height: 1.3">{icon(kind)}<span><span style="font-weight: 700">{esc(strong)}'
            f"</span> {esc(rest)}</span></div>"
        )

    rows = []
    if c["type"] == "promo":
        rows.append(row("link", "Link in bio", "to explore the resource."))
    else:
        save = close.get("save", "Save this for later.")
        if not save.startswith("Save this"):
            raise BuildError('close.save must start with "Save this"')
        rows.append(row("save", "Save this", save[len("Save this"):].strip()))
    rows.append(row("follow", f"Follow {HANDLE}", "for one small step at a time."))
    parts = [
        f'<h2 style="margin: 0; font-family: {SERIF}; font-weight: 700; font-size: 100px; '
        f'line-height: 1.1; letter-spacing: -1px">{ANCHOR}</h2>',
        '<div style="display: flex; flex-direction: column; gap: 20px">' + "".join(rows) + "</div>",
    ]
    if close.get("safety"):
        parts.append(
            f'<div style="background: {CREAM}; color: {INK}; border-radius: 28px; '
            f'padding: 36px 40px; font-size: 34px; line-height: 1.4">{SAFETY}</div>'
        )
    decor = circle(WHITE, 0.08, 620, "right: -200px; top: -180px")
    return frame(
        total, total, c["label"], DEEP, WHITE, decor, "\n".join(parts), "<div></div>", dark=True
    )


def build_caption(c):
    tags = c.get("hashtags", [])
    if not 5 <= len(tags) <= 8:
        raise BuildError("needs 5 to 8 hashtags")
    if any(not re.fullmatch(r"#\w+", t) for t in tags):
        raise BuildError("each hashtag must look like #word")
    text = c["caption"].strip()
    if c["type"] == "promo":
        if "link in bio" not in text.lower():
            raise BuildError('a promo caption must say "link in bio"')
        text += (
            f"\n\n{DISCLOSURE} {c['resource']['name']} is a self-help program, "
            "not professional counseling."
        )
    return text + "\n\n" + " ".join(tags) + "\n"


def build(folder):
    c = json.loads((folder / "carousel.json").read_text(encoding="utf-8"))
    kind = c.get("type")
    if kind not in ("useful", "promo"):
        raise BuildError('type must be "useful" or "promo"')
    want = 5 if kind == "useful" else 4
    if len(c.get("points", [])) != want:
        raise BuildError(f"a {kind} carousel needs exactly {want} points")
    if kind == "promo" and not c.get("resource"):
        raise BuildError("a promo carousel needs a resource")
    if kind == "useful" and c.get("resource"):
        raise BuildError("a useful carousel must not name a resource")

    total = 7
    pages = [cover_slide(c, total)]
    pages += [point_slide(c, i, total) for i in range(want)]
    if kind == "promo":
        pages.append(resource_slide(c, 6, total))
    pages.append(close_slide(c, total))

    slides = folder / "slides"
    slides.mkdir(exist_ok=True)
    for old in slides.glob("*.html"):
        old.unlink()
    for i, page in enumerate(pages, 1):
        (slides / f"{i:02d}.html").write_text(page, encoding="utf-8")
    (folder / "caption.txt").write_text(build_caption(c), encoding="utf-8")


def main():
    wanted = set(sys.argv[1:])
    folders = sorted(
        p for p in DRAFTS.iterdir() if (p / "carousel.json").is_file()
    ) if DRAFTS.is_dir() else []
    failed = False
    for folder in folders:
        if wanted and folder.name not in wanted:
            continue
        try:
            build(folder)
            print(f"built  drafts/{folder.name}")
        except (BuildError, KeyError, ValueError) as err:
            failed = True
            print(f"FAIL   drafts/{folder.name}: {err}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
