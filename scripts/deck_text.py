#!/usr/bin/env python3
"""Extract the text of every deck (.pptx) and document (.docx) in lgtm-presentation/
into Markdown copies under lgtm-presentation/text/<basename>.md.

Standard library only (zipfile + xml.etree), so it runs unchanged in CI.

Usage:
    deck_text.py --write [--root DIR]      regenerate lgtm-presentation/text/*.md
    deck_text.py --check [--root DIR]      regenerate in memory and compare; exit 1 on drift,
                                           a missing or extra text file, or slides without notes
    deck_text.py --check --allow-missing-notes
                                           report missing notes but do not fail on them
                                           (transition aid; KNOWN_MISSING_NOTES below is the
                                           per-deck list of exceptions that the batches empty)
    deck_text.py                           print this usage

Output format (pptx)
    # <basename>            then a source line
    ## [NNN] EYEBROW · Title (sldId N)   one section per slide, in presentation order
    body paragraphs         shape order in spTree, groups recursed, tables flattened row by row
                            (cells joined with " | "), bullets as "- " / "1. "
    [chip] python · FastAPI the language chip that sits above a code box
    ```python ... ```       code boxes (see heuristics)
    p. 12                   the static page-number text box
    > notes                 speaker notes (notesSlide body placeholder), one ">" block

Heuristics
    Title    the title / ctrTitle placeholder if present; otherwise the non-monospace text shape
             with the largest run font size (ties: first in shape order). Multi-line titles are
             joined with a space.
    Eyebrow  the first text shape before the title that is a single line of at most 60
             characters with a largest font size of 14 pt or less (the red kicker line). Absent
             on decks that have none.
    Code     a shape whose non-empty runs are all monospace (font name matches Mono, Courier,
             Consolas, Menlo, Monaco). A single-paragraph monospace shape of at most 11 pt and
             60 characters is a chip, not code; its language is the text before " · ", lower
             cased, and tags the next code box in the same container.
    Page     a shape whose whole text is 1 to 3 digits at 11 pt or less.

Output is deterministic: normalised whitespace, LF endings, trailing newline. Jekyll is told to
exclude lgtm-presentation/, but any `{{` or `{%` is still wrapped in {% raw %} so a stray include of
these files cannot be interpreted as Liquid and the site validator's brace rules hold.
"""
from __future__ import annotations

import argparse
import difflib
import posixpath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

MONO_RE = re.compile(r"mono|courier|consolas|menlo|monaco", re.I)
REPO = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = REPO / "lgtm-presentation"

# Decks allowed to have slides without notes while the S12 batches run: {basename: [slide numbers]}.
# Each batch removes its entry; the final state is an empty dict.
KNOWN_MISSING_NOTES: dict[str, list[int]] = {
}


def q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def norm(s: str) -> str:
    return re.sub(r"[ \t ]+", " ", s).strip()


def guard_liquid(text: str) -> str:
    """Wrap a one-line paragraph holding Liquid delimiters in {% raw %}."""
    if "{{" in text or "{%" in text:
        return "{% raw %}" + text + "{% endraw %}"
    return text


def fence(code: str, lang: str = "") -> list[str]:
    ticks = "```"
    while ticks in code:
        ticks += "`"
    out = [ticks + lang] + code.split("\n") + [ticks]
    if "{{" in code or "{%" in code:
        out = ["{% raw %}"] + out + ["{% endraw %}"]
    return out


# ---------------------------------------------------------------- pptx

def rels_of(z: zipfile.ZipFile, part: str) -> dict[str, tuple[str, str]]:
    d, b = posixpath.split(part)
    rp = posixpath.join(d, "_rels", b + ".rels")
    out: dict[str, tuple[str, str]] = {}
    if rp not in z.namelist():
        return out
    for rel in ET.fromstring(z.read(rp)):
        tgt = rel.get("Target", "")
        if rel.get("TargetMode") != "External":
            tgt = posixpath.normpath(posixpath.join(d, tgt)) if not tgt.startswith("/") else tgt[1:]
        out[rel.get("Id", "")] = (rel.get("Type", "").rsplit("/", 1)[-1], tgt)
    return out


class Para:
    __slots__ = ("text", "mono", "size", "bullet", "level")

    def __init__(self, text, mono, size, bullet, level):
        self.text, self.mono, self.size, self.bullet, self.level = text, mono, size, bullet, level


def para_of(p: ET.Element) -> Para:
    parts: list[str] = []
    mono_flags: list[bool] = []
    size = 0
    for el in p:
        if el.tag == q(A, "r") or el.tag == q(A, "fld"):
            t = el.find(q(A, "t"))
            txt = t.text or "" if t is not None else ""
            parts.append(txt)
            if txt.strip():
                rpr = el.find(q(A, "rPr"))
                font = None
                if rpr is not None:
                    lat = rpr.find(q(A, "latin"))
                    font = lat.get("typeface") if lat is not None else None
                    if rpr.get("sz"):
                        size = max(size, int(rpr.get("sz")))
                mono_flags.append(bool(font and MONO_RE.search(font)))
        elif el.tag == q(A, "br"):
            parts.append("\n")
    bullet = ""
    ppr = p.find(q(A, "pPr"))
    level = 0
    if ppr is not None:
        level = int(ppr.get("lvl") or 0)
        if ppr.find(q(A, "buChar")) is not None:
            bullet = "- "
        elif ppr.find(q(A, "buAutoNum")) is not None:
            bullet = "1. "
    return Para("".join(parts), bool(mono_flags) and all(mono_flags), size, bullet, level)


class Item:
    """One text unit from a slide: kind in text|code|chip|table|page, with shape metadata."""
    def __init__(self, kind, lines, size=0, title_ph=False, raw=""):
        self.kind, self.lines, self.size, self.title_ph, self.raw = kind, lines, size, title_ph, raw


def text_lines(paras: list[Para]) -> list[str]:
    out = []
    for p in paras:
        lines = [norm(x) for x in p.text.split("\n")]
        lines = [x for x in lines if x]
        if not lines:
            continue
        pre = "  " * p.level + p.bullet if p.bullet else ""
        out.append(pre + "\n".join(lines))
    return out


def shape_items(el: ET.Element, items: list[Item]) -> None:
    if el.tag == q(P, "grpSp"):
        for c in el:
            shape_items(c, items)
        return
    if el.tag == q(P, "graphicFrame"):
        tbl = el.find(f".//{q(A, 'tbl')}")
        if tbl is not None:
            rows = []
            for tr in tbl.findall(q(A, "tr")):
                cells = []
                for tc in tr.findall(q(A, "tc")):
                    tx = tc.find(q(A, "txBody"))
                    ps = [para_of(p) for p in tx.findall(q(A, "p"))] if tx is not None else []
                    cells.append(norm(" ".join(l for l in text_lines(ps)).replace("\n", " ")))
                rows.append(" | ".join(cells))
            items.append(Item("table", rows))
        return
    if el.tag != q(P, "sp"):
        return
    tx = el.find(q(P, "txBody"))
    if tx is None:
        return
    paras = [para_of(p) for p in tx.findall(q(A, "p"))]
    nonempty = [p for p in paras if p.text.strip()]
    if not nonempty:
        return
    ph = el.find(f"{q(P, 'nvSpPr')}/{q(P, 'nvPr')}/{q(P, 'ph')}")
    title_ph = ph is not None and ph.get("type") in ("title", "ctrTitle")
    size = max(p.size for p in nonempty)
    full = "\n".join(p.text.strip("\n") for p in nonempty)
    if all(p.mono for p in nonempty):
        one_line = len(nonempty) == 1 and "\n" not in nonempty[0].text.strip()
        if one_line and size <= 1100 and len(full) <= 60:
            items.append(Item("chip", [norm(full)], size))
        else:
            code = "\n".join(re.sub(r"[ \t]+$", "", p.text.replace(" ", " ").rstrip("\n")) for p in nonempty)
            items.append(Item("code", code.split("\n"), size, raw=code))
        return
    if len(nonempty) == 1 and size <= 1100 and re.fullmatch(r"\d{1,3}", nonempty[0].text.strip()):
        items.append(Item("page", [nonempty[0].text.strip()], size))
        return
    items.append(Item("text", text_lines(paras), size, title_ph))


def lang_of(chip: str) -> str:
    head = chip.split("·")[0].strip().lower()
    head = re.sub(r"[^a-z0-9+#.-]", "", head)
    return head


def slide_section(z: zipfile.ZipFile, part: str, idx: int, sld_id: str, rels: dict) -> tuple[str, bool]:
    root = ET.fromstring(z.read(part))
    tree = root.find(f"{q(P, 'cSld')}/{q(P, 'spTree')}")
    items: list[Item] = []
    for c in tree:
        shape_items(c, items)
    # title
    title_i = next((i for i, it in enumerate(items) if it.kind == "text" and it.title_ph), None)
    if title_i is None:
        best = 0
        for i, it in enumerate(items):
            if it.kind == "text" and it.size > best:
                best, title_i = it.size, i
        if title_i is None:
            title_i = next((i for i, it in enumerate(items) if it.kind == "text"), None)
    title = norm(" ".join(items[title_i].lines)) if title_i is not None else "(untitled)"
    eyebrow_i = None
    for i, it in enumerate(items[: title_i if title_i is not None else 0]):
        if it.kind == "text" and len(it.lines) == 1 and "\n" not in it.lines[0] and len(it.lines[0]) <= 60 \
                and 0 < it.size <= 1400:
            eyebrow_i = i
            break
    head = f"{items[eyebrow_i].lines[0]} · {title}" if eyebrow_i is not None else title
    out = [f"## [{idx:03d}] {head} (sldId {sld_id})", ""]
    pending_chip = None
    for i, it in enumerate(items):
        if i == title_i or i == eyebrow_i:
            continue
        if it.kind == "chip":
            if pending_chip:
                out += [guard_liquid("[chip] " + pending_chip), ""]
            pending_chip = it.lines[0]
        elif it.kind == "code":
            lang = lang_of(pending_chip) if pending_chip else ""
            if pending_chip:
                out += [guard_liquid("[chip] " + pending_chip), ""]
                pending_chip = None
            out += fence("\n".join(it.lines), lang) + [""]
        elif it.kind == "page":
            out += [f"p. {it.lines[0]}", ""]
        else:  # text, table
            for ln in it.lines:
                out += [guard_liquid(ln), ""]
    if pending_chip:
        out += [guard_liquid("[chip] " + pending_chip), ""]
    notes_text = ""
    has_notes = False
    for rid, (typ, tgt) in rels.items():
        if typ == "notesSlide" and tgt in z.namelist():
            nroot = ET.fromstring(z.read(tgt))
            for sp in nroot.iter(q(P, "sp")):
                ph = sp.find(f"{q(P, 'nvSpPr')}/{q(P, 'nvPr')}/{q(P, 'ph')}")
                if ph is not None and ph.get("type") == "body":
                    tx = sp.find(q(P, "txBody"))
                    ps = [para_of(p) for p in tx.findall(q(A, "p"))]
                    lines = text_lines(ps)
                    if lines:
                        notes_text = "\n".join(lines)
                    break
    if notes_text:
        has_notes = True
        nl = []
        for para in notes_text.split("\n"):
            nl += ["> " + guard_liquid(para), ">"]
        out += nl[:-1] + [""]
    # keep list items together: drop the blank line between two consecutive bullets
    tight = []
    for i, ln in enumerate(out):
        if ln == "" and tight and i + 1 < len(out) and re.match(r"\s*(- |\d+\. )", tight[-1]) \
                and re.match(r"\s*(- |\d+\. )", out[i + 1]):
            continue
        tight.append(ln)
    return "\n".join(tight), has_notes


def pptx_to_md(path: Path) -> tuple[str, list[int]]:
    """Return (markdown, [slide numbers without notes])."""
    with zipfile.ZipFile(path) as z:
        pres = ET.fromstring(z.read("ppt/presentation.xml"))
        prels = rels_of(z, "ppt/presentation.xml")
        lst = pres.find(q(P, "sldIdLst"))
        sections = []
        missing = []
        n = 0
        for sid in lst:
            n += 1
            typ, part = prels[sid.get(q(R, "id"))]
            sec, has = slide_section(z, part, n, sid.get("id"), rels_of(z, part))
            sections.append(sec)
            if not has:
                missing.append(n)
    head = [f"# {path.stem}", "", f"Source: {path.name} · {n} slides", ""]
    return "\n".join(head) + "\n" + "\n".join(sections).rstrip("\n") + "\n", missing


# ---------------------------------------------------------------- docx

def docx_to_md(path: Path) -> tuple[str, list[int]]:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
        styles = ET.fromstring(z.read("word/styles.xml")) if "word/styles.xml" in z.namelist() else None
    style_mono = set()
    if styles is not None:
        for st in styles.findall(q(W, "style")):
            rf = st.find(f"{q(W, 'rPr')}/{q(W, 'rFonts')}")
            name = st.find(q(W, "name"))
            sid = st.get(q(W, "styleId"), "")
            if (rf is not None and MONO_RE.search(rf.get(q(W, "ascii"), ""))) or \
                    (name is not None and re.fullmatch(r"(macro text|code|source code|preformatted.*)", name.get(q(W, "val"), ""), re.I)):
                style_mono.add(sid)

    def runs_of(p):
        out = []
        for r in p.iter(q(W, "r")):
            txt = ""
            for c in r:
                if c.tag == q(W, "t"):
                    txt += c.text or ""
                elif c.tag == q(W, "tab"):
                    txt += "\t"
                elif c.tag in (q(W, "br"), q(W, "cr")):
                    txt += "\n"
            rf = r.find(f"{q(W, 'rPr')}/{q(W, 'rFonts')}")
            mono = bool(rf is not None and MONO_RE.search(rf.get(q(W, "ascii"), "") + rf.get(q(W, "hAnsi"), "")))
            out.append((txt, mono))
        return out

    def para(p):
        ps = p.find(f"{q(W, 'pPr')}/{q(W, 'pStyle')}")
        style = ps.get(q(W, "val")) if ps is not None else ""
        runs = [(t, m) for t, m in runs_of(p)]
        pm = style in style_mono
        visible = [(t, m) for t, m in runs if t.strip()]
        all_mono = pm or (bool(visible) and all(m for _, m in visible))
        if all_mono:
            return style, "".join(t for t, _ in runs).rstrip("\n"), True
        buf, i = "", 0
        while i < len(runs):
            t, m = runs[i]
            if m and t.strip():
                j, seg = i, ""
                while j < len(runs) and (runs[j][1] or not runs[j][0].strip()):
                    seg += runs[j][0]
                    j += 1
                buf += "`" + seg.strip() + "`" + (" " if seg.endswith(" ") else "")
                i = j
            else:
                buf += t
                i += 1
        return style, buf, False

    out = [f"# {path.stem}", "", f"Source: {path.name}", ""]
    code: list[str] = []
    num = 0

    def flush():
        nonlocal code
        if code:
            out.extend(fence("\n".join(code)) + [""])
            code = []

    body = root.find(q(W, "body"))
    for el in body:
        if el.tag == q(W, "p"):
            style, text, mono = para(el)
            if mono:
                if text.strip():
                    num = 0
                    code.append(text.replace(" ", " ").rstrip())
                continue
            flush()
            text = "\n".join(norm(x) for x in text.split("\n")).strip()
            if not text:
                continue
            m = re.fullmatch(r"Heading(\d)", style)
            if style == "Title":
                out += ["# " + text, ""]
            elif m:
                out += ["#" * int(m.group(1)) + " " + guard_liquid(text), ""]
            elif style.startswith("ListBullet"):
                lvl = int(style[10:] or 1) - 1
                num = 0
                out += ["  " * lvl + "- " + guard_liquid(text)]
                continue
            elif style.startswith("ListNumber"):
                num += 1
                lvl = int(style[10:] or 1) - 1
                out += ["  " * lvl + f"{num}. " + guard_liquid(text)]
                continue
            else:
                out += [guard_liquid(text), ""]
            num = 0
        elif el.tag == q(W, "tbl"):
            flush()
            if out and out[-1] != "":
                out.append("")
            for tr in el.iter(q(W, "tr")):
                cells = []
                for tc in tr.findall(q(W, "tc")):
                    cells.append(norm(" ".join(para(p)[1].replace("\n", " ") for p in tc.iter(q(W, "p")) if para(p)[1].strip())))
                out.append(guard_liquid(" | ".join(cells)))
            out.append("")
            num = 0
        # list items are tight; close the list with a blank line before the next non-list block
        if out and out[-1] != "" and el.tag == q(W, "p"):
            nxt = el.getnext()
            if nxt is None or nxt.tag != q(W, "p") or not _is_list(nxt):
                out.append("")
    flush()
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"
    return text, []


def _is_list(p: ET.Element) -> bool:
    ps = p.find(f"{q(W, 'pPr')}/{q(W, 'pStyle')}")
    return ps is not None and ps.get(q(W, "val"), "").startswith(("ListBullet", "ListNumber"))


# ---------------------------------------------------------------- driver

def extract_all(root: Path) -> tuple[dict[str, str], dict[str, list[int]]]:
    files, missing = {}, {}
    for f in sorted(root.glob("*.pptx")):
        md, miss = pptx_to_md(f)
        files[f.stem + ".md"] = md
        missing[f.stem] = miss
    for f in sorted(root.glob("*.docx")):
        md, _ = docx_to_md(f)
        files[f.stem + ".md"] = md
    return files, missing


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Extract deck text to lgtm-presentation/text/*.md",
                                 usage="deck_text.py (--write | --check [--allow-missing-notes]) [--root DIR]")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--allow-missing-notes", action="store_true")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="the lgtm-presentation directory")
    args = ap.parse_args(argv)
    if not (args.write or args.check):
        print(__doc__)
        return 0
    root: Path = args.root
    outdir = root / "text"
    files, missing = extract_all(root)
    if args.write:
        outdir.mkdir(exist_ok=True)
        for name in {p.name for p in outdir.glob("*.md")} - set(files):
            (outdir / name).unlink()
        for name, md in files.items():
            (outdir / name).write_bytes(md.encode("utf-8"))
        for name, md in files.items():
            print(f"wrote {outdir / name} ({len(md.encode('utf-8'))} bytes)")
        return 0
    rc = 0
    on_disk = {p.name for p in outdir.glob("*.md")} if outdir.is_dir() else set()
    for name in sorted(set(files) | on_disk):
        if name not in on_disk:
            print(f"MISSING text copy: {outdir / name}")
            rc = 1
        elif name not in files:
            print(f"EXTRA text copy (no source deck): {outdir / name}")
            rc = 1
        else:
            cur = (outdir / name).read_text(encoding="utf-8")
            if cur != files[name]:
                diff = list(difflib.unified_diff(cur.splitlines(), files[name].splitlines(),
                                                 f"text/{name} (committed)", f"text/{name} (regenerated)", lineterm="", n=1))
                print(f"STALE text copy: {outdir / name} ({len(diff)} diff lines; first 40 follow)")
                print("\n".join(diff[:40]))
                rc = 1
    for deck, miss in sorted(missing.items()):
        known = set(KNOWN_MISSING_NOTES.get(deck, []))
        unexpected = [n for n in miss if n not in known]
        stale_known = [n for n in known if n not in miss]
        if unexpected:
            print(f"NOTES missing in {deck}: slides {unexpected}")
            rc = 1
        if stale_known:
            print(f"KNOWN_MISSING_NOTES entry now has notes (remove it) in {deck}: slides {stale_known}")
            rc = 1
        if known and (set(miss) & known):
            print(f"note: {deck} still has {len(set(miss) & known)} allowed slides without notes")
            if not args.allow_missing_notes:
                rc = 1
    print("deck_text --check:", "FAILED" if rc else "ok")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
