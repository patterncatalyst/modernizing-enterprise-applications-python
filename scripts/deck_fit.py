#!/usr/bin/env python3
"""Detect text that does not fit its shape in a rendered deck (python-pptx; run with the S12 venv).

    deck_fit.py <deck.pptx> [--pdf PATH] [--keep-pdf DIR] [--slides 45,88] [--tol PT] [--json]

LibreOffice (soffice, headless) converts the deck to PDF unless --pdf gives an existing render of
the same deck; `pdftotext -bbox-layout` then gives the rendered line and word boxes. Each rendered
line is matched to the slide shape it belongs to (its text must occur in the shape's text; ties and
short fragments are resolved by geometry: the frame that contains it, otherwise the nearest frame
above it in the same column), and the slide geometry (EMU, 12700 per PDF point) is compared with
the rendered boxes. A flag is raised for

  overflow-bottom / overflow-right / overflow-top / overflow-left
                 text outside its own shape's frame by more than --tol points (default 1.5);
                 the frame is the shape's box, insets included, so text in the inset band is fine
  furniture      text of another shape overlapping the page-number box (a 1-3 digit text box at
                 11 pt or less) or the logo picture (a picture inside the bottom 15 % of the
                 slide, narrower than a quarter of it)
  off-slide      text outside the slide
  collision-with-N
                 text of this shape overlapping rendered text of shape N (boxes overlap by more than a
                 quarter of the smaller line height, and 1 pt across)

Shapes whose body autofits by growing (spAutoFit) are not checked against their own bottom edge
(LibreOffice grows the frame); they still get the furniture and off-slide checks. Rotated shapes
are skipped. Tables (graphicFrame) are checked like shapes against their frame. Hidden slides are
not exported by LibreOffice and are skipped. Brand fonts must be installed (a render with
substituted fonts hides or invents overflow):
    sudo dnf install -y redhat-text-fonts redhat-display-fonts overpass-fonts

Output: one line per flag ("slide 45 (sldId 300) shape 509 'Google Shape;509;p47': overflow-bottom
by 9.8 pt: '...'"), then a summary; --json prints a JSON list instead. Exit 0 when nothing is
flagged, 1 when something is, 2 on a usage or render error.
Environment: LO_PROFILE sets the LibreOffice profile directory (as in deck_render.sh).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

EMU_PER_PT = 12700
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def q(ns, tag):
    return f"{{{ns}}}{tag}"


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"\s+", "", s)


class Box:
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    def contains(self, x, y, pad=0.0):
        return self.x0 - pad <= x <= self.x1 + pad and self.y0 - pad <= y <= self.y1 + pad

    def intersects(self, o, pad=0.0, pad_y=None):
        return (min(self.x1, o.x1) - max(self.x0, o.x0) > pad
                and min(self.y1, o.y1) - max(self.y0, o.y0) > (pad if pad_y is None else pad_y))


class TShape:
    def __init__(self, sid, name, box, text, autogrow, page_number=False):
        self.sid, self.name, self.box = sid, name, box
        self.text = text
        self.ntext = norm(text)
        self.autogrow = autogrow
        self.page_number = page_number


# ----------------------------------------------------------------- slide geometry

def _xfrm_map(grp_el):
    """Child-to-parent mapping of a group: (sx, sy, dx, dy) in EMU."""
    x = grp_el.find(f"{q(P, 'grpSpPr')}/{q(A, 'xfrm')}")
    if x is None:
        return 1.0, 1.0, 0.0, 0.0
    off, ext = x.find(q(A, "off")), x.find(q(A, "ext"))
    choff, chext = x.find(q(A, "chOff")), x.find(q(A, "chExt"))
    if off is None or ext is None or choff is None or chext is None:
        return 1.0, 1.0, 0.0, 0.0
    cw, ch = int(chext.get("cx")) or 1, int(chext.get("cy")) or 1
    sx, sy = int(ext.get("cx")) / cw, int(ext.get("cy")) / ch
    return sx, sy, int(off.get("x")) - int(choff.get("x")) * sx, int(off.get("y")) - int(choff.get("y")) * sy


def _rotated(sh):
    x = sh._element.find(f".//{q(A, 'xfrm')}")
    return x is not None and int(x.get("rot", "0") or 0) % 21600000 != 0


def _run_sizes(el):
    return [int(r.get("sz")) for r in el.iter(q(A, "rPr")) if r.get("sz")]


def collect(shapes, tf=(1.0, 1.0, 0.0, 0.0), out=None, skipped=None):
    """Text shapes, tables and pictures of a shape tree, with frames in PDF points."""
    out = out if out is not None else {"text": [], "pics": []}
    skipped = skipped if skipped is not None else []
    sx, sy, dx, dy = tf
    for sh in shapes:
        if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
            gsx, gsy, gdx, gdy = _xfrm_map(sh._element)
            collect(sh.shapes, (sx * gsx, sy * gsy, sx * gdx + dx, sy * gdy + dy), out, skipped)
            continue
        if sh.left is None or sh.top is None or sh.width is None or sh.height is None:
            continue
        x0 = (sh.left * sx + dx) / EMU_PER_PT
        y0 = (sh.top * sy + dy) / EMU_PER_PT
        box = Box(x0, y0, x0 + sh.width * sx / EMU_PER_PT, y0 + sh.height * sy / EMU_PER_PT)
        if sh.shape_type == MSO_SHAPE_TYPE.PICTURE:
            out["pics"].append((sh.shape_id, sh.name, box))
            continue
        el = sh._element
        if getattr(sh, "has_table", False) and sh.has_table:
            text = "\n".join(t.text or "" for t in el.iter(q(A, "t")))
            if text.strip():
                out["text"].append(TShape(sh.shape_id, sh.name, box, text, autogrow=True))
            continue
        if not getattr(sh, "has_text_frame", False) or not sh.has_text_frame:
            continue
        text = "\n".join("".join(t.text or "" for t in p.iter(q(A, "t"))) for p in el.iter(q(A, "p")))
        if not text.strip():
            continue
        if _rotated(sh):
            skipped.append(sh.shape_id)
            continue
        body = el.find(f"{q(P, 'txBody')}/{q(A, 'bodyPr')}")
        autogrow = body is not None and body.find(q(A, "spAutoFit")) is not None
        sizes = _run_sizes(el)
        pnum = bool(re.fullmatch(r"\d{1,3}", text.strip())) and 0 < max(sizes or [0]) <= 1100
        out["text"].append(TShape(sh.shape_id, sh.name, box, text, autogrow, pnum))
    return out, skipped


# ----------------------------------------------------------------- render

WORD_RE = re.compile(r'<word xMin="([\d.\-]+)" yMin="([\d.\-]+)" xMax="([\d.\-]+)" yMax="([\d.\-]+)">(.*?)</word>')
LINE_RE = re.compile(r'<line xMin="([\d.\-]+)" yMin="([\d.\-]+)" xMax="([\d.\-]+)" yMax="([\d.\-]+)">')
PAGE_RE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">')


def parse_bbox(xml_text):
    """Pages of lines; a line is (Box, [(Box, word), ...])."""
    pages = []
    line = None
    for tok in re.finditer(r"<page [^>]*>|<line [^>]*>|<word [^>]*>.*?</word>|</line>", xml_text):
        t = tok.group(0)
        if t.startswith("<page"):
            m = PAGE_RE.match(t)
            pages.append({"w": float(m.group(1)), "h": float(m.group(2)), "lines": []})
        elif t.startswith("<line"):
            m = LINE_RE.match(t)
            line = (Box(*map(float, m.groups())), [])
            pages[-1]["lines"].append(line)
        elif t.startswith("<word"):
            m = WORD_RE.match(t)
            b = Box(*map(float, m.groups()[:4]))
            line[1].append((b, html.unescape(m.group(5))))
    return pages


def check_fonts():
    try:
        fonts = subprocess.run(["fc-list"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return []
    return [f for f in ("Red Hat Text", "Red Hat Display", "Red Hat Mono", "Overpass")
            if f.lower() not in fonts.lower()]


def render_pdf(deck, outdir):
    profile = os.environ.get("LO_PROFILE") or str(Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "deck_render" / "lo-profile")
    Path(profile).mkdir(parents=True, exist_ok=True)
    subprocess.run(["soffice", "--headless", f"-env:UserInstallation=file://{profile}", "--convert-to", "pdf",
                    "--outdir", str(outdir), str(deck)], check=True, capture_output=True)
    pdf = Path(outdir) / (Path(deck).stem + ".pdf")
    if not pdf.is_file():
        raise RuntimeError(f"soffice produced no PDF for {deck}")
    return pdf


# ----------------------------------------------------------------- matching and checks

def owner(seg_text, seg_box, shapes):
    """The shape a rendered text segment belongs to, or None."""
    t = norm(seg_text)
    if not t:
        return None
    cands = [s for s in shapes if t in s.ntext]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    cx, cy = (seg_box.x0 + seg_box.x1) / 2, (seg_box.y0 + seg_box.y1) / 2
    inside = [s for s in cands if s.box.contains(cx, cy)]
    if inside:
        # the smallest containing frame (a code box inside a backdrop, a chip inside a code box)
        return min(inside, key=lambda s: (s.box.x1 - s.box.x0) * (s.box.y1 - s.box.y0))
    column = [s for s in cands if min(s.box.x1, seg_box.x1) - max(s.box.x0, seg_box.x0) > 0]
    above = [s for s in column if s.box.y0 <= seg_box.y0]
    if above:
        return min(above, key=lambda s: seg_box.y0 - s.box.y1)
    below = [s for s in column if s.box.y1 >= seg_box.y1]
    if below:
        return min(below, key=lambda s: s.box.y0 - seg_box.y1)
    return min(cands, key=lambda s: abs(cx - (s.box.x0 + s.box.x1) / 2) + abs(cy - (s.box.y0 + s.box.y1) / 2))


def segments(line, shapes):
    """Split a rendered line into (shape, box, text) segments: the whole line when its text occurs
    in one shape, otherwise word by word (a leading bullet glyph is dropped first)."""
    lbox, words = line
    if not words:
        return []
    for start in (0, 1):
        ws = words[start:]
        if not ws:
            break
        text = "".join(w for _, w in ws)
        box = Box(min(b.x0 for b, _ in ws), min(b.y0 for b, _ in ws),
                  max(b.x1 for b, _ in ws), max(b.y1 for b, _ in ws))
        sh = owner(text, box, shapes)
        if sh is not None:
            return [(sh, box, " ".join(w for _, w in ws))]
    return [(owner(w, b, shapes), b, w) for b, w in words]


def check_slide(page, shapes, pics, slide_w, slide_h, tol):
    flags = []
    furniture = [("page-number", s.box) for s in shapes if s.page_number]
    for pid, pname, b in pics:
        if b.y0 >= slide_h * 0.85 and (b.x1 - b.x0) < slide_w * 0.25:
            furniture.append(("logo", b))
    seen = set()

    def add(sh, kind, amount, text):
        key = (sh.sid if sh else None, kind)
        if key in seen:
            # one flag per shape and kind; keep the worst amount
            for f in flags:
                if (f["shape_id"], f["kind"]) == key and amount > f["by_pt"]:
                    f["by_pt"], f["text"] = round(amount, 1), text[:70]
            return
        seen.add(key)
        flags.append({"shape_id": sh.sid if sh else None, "shape": sh.name if sh else None,
                      "kind": kind, "by_pt": round(amount, 1), "text": text[:70]})

    segs = [seg for line in page["lines"] for seg in segments(line, shapes)]
    for i, (sh, b, text) in enumerate(segs):
        if sh is None:
            continue
        for sh2, b2, text2 in segs[i + 1:]:
            # word boxes carry the font's ascent and descent padding; glyphs touch only when
            # the boxes overlap by more than about a quarter of the smaller box's height
            pad_y = max(2.0, 0.25 * min(b.y1 - b.y0, b2.y1 - b2.y0))
            if sh2 is not None and sh2 is not sh and b.intersects(b2, pad=1.0, pad_y=pad_y):
                a_, z_ = (sh, sh2) if sh.sid < sh2.sid else (sh2, sh)
                add(z_, f"collision-with-{a_.sid}", min(b.y1, b2.y1) - max(b.y0, b2.y0),
                    text if z_ is sh else text2)
    for sh, b, text in segs:
        if b.x0 < -tol or b.y0 < -tol or b.x1 > slide_w + tol or b.y1 > slide_h + tol:
            add(sh, "off-slide", max(-b.x0, -b.y0, b.x1 - slide_w, b.y1 - slide_h), text)
        if sh is None:
            continue
        f = sh.box
        # a word box spans the font's ascent and descent, about 1.3 x the size, while the line
        # pitch LibreOffice lays out is 1.2 x the size: allow that difference on top of --tol
        t_v = max(tol, 0.12 * (b.y1 - b.y0))
        if b.y1 > f.y1 + t_v and not sh.autogrow:
            add(sh, "overflow-bottom", b.y1 - f.y1, text)
        if b.x1 > f.x1 + tol:
            add(sh, "overflow-right", b.x1 - f.x1, text)
        if b.y0 < f.y0 - t_v and not sh.autogrow:
            add(sh, "overflow-top", f.y0 - b.y0, text)
        if b.x0 < f.x0 - tol:
            add(sh, "overflow-left", f.x0 - b.x0, text)
        if sh.page_number:
            continue
        for kind, fb in furniture:
            if b.intersects(fb, pad=0.5):
                add(sh, f"furniture-{kind}", min(b.y1, fb.y1) - max(b.y0, fb.y0), text)
    return flags


def main(argv):
    ap = argparse.ArgumentParser(description="Detect text that does not fit its shape in a rendered deck")
    ap.add_argument("deck", type=Path)
    ap.add_argument("--pdf", type=Path, help="an existing soffice PDF of this deck (skips the render)")
    ap.add_argument("--keep-pdf", type=Path, help="directory to keep the rendered PDF in")
    ap.add_argument("--slides", help="comma-separated 1-based slide numbers to check (default: all)")
    ap.add_argument("--tol", type=float, default=1.5, help="tolerance in points (default 1.5)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.deck.is_file():
        print(f"deck_fit: {args.deck} not found", file=sys.stderr)
        return 2
    tmp = None
    try:
        if args.pdf:
            pdf = args.pdf
        else:
            missing = check_fonts()
            if missing:
                print(f"deck_fit: missing brand font(s): {', '.join(missing)}", file=sys.stderr)
                return 2
            outdir = args.keep_pdf or Path(tempfile.mkdtemp(prefix="deck_fit_"))
            if not args.keep_pdf:
                tmp = outdir
            outdir.mkdir(parents=True, exist_ok=True)
            pdf = render_pdf(args.deck, outdir)
        xml_text = subprocess.run(["pdftotext", "-bbox-layout", str(pdf), "-"], check=True,
                                  capture_output=True, text=True).stdout
    except (subprocess.CalledProcessError, RuntimeError, FileNotFoundError) as e:
        print(f"deck_fit: render failed: {e}", file=sys.stderr)
        return 2
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    pages = parse_bbox(xml_text)
    prs = Presentation(str(args.deck))
    sw, sh_ = prs.slide_width / EMU_PER_PT, prs.slide_height / EMU_PER_PT
    visible = [(i, s) for i, s in enumerate(prs.slides, 1) if s._element.get("show") not in ("0", "false")]
    if len(visible) != len(pages):
        print(f"deck_fit: {len(visible)} visible slides but {len(pages)} PDF pages", file=sys.stderr)
        return 2
    want = {int(n) for n in args.slides.split(",")} if args.slides else None
    results = []
    for (num, slide), page in zip(visible, pages):
        if want and num not in want:
            continue
        if abs(page["w"] - sw) > 1 or abs(page["h"] - sh_) > 1:
            print(f"deck_fit: page {num} is {page['w']}x{page['h']} pt, slide is {sw:.1f}x{sh_:.1f}", file=sys.stderr)
            return 2
        got, _ = collect(slide.shapes)
        for f in check_slide(page, got["text"], got["pics"], sw, sh_, args.tol):
            f.update({"slide": num, "sldId": slide.slide_id})
            results.append(f)
    if args.json:
        print(json.dumps(results, indent=1, ensure_ascii=False))
    else:
        for f in results:
            print(f"slide {f['slide']} (sldId {f['sldId']}) shape {f['shape_id']} {f['shape']!r}: "
                  f"{f['kind']} by {f['by_pt']} pt: {f['text']!r}")
        n = len({f['slide'] for f in results})
        print(f"deck_fit: {args.deck.name}: {len(results)} flag(s) on {n} slide(s)")
    return 1 if results else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
