#!/usr/bin/env python3
"""Retarget title fonts from Overpass to Red Hat Display across a .pptx, in place.

    deck_font.py <deck.pptx> [--apply] [--out PATH]

Without --apply, prints a report: how many font-carrying elements (a:latin, a:ea, a:cs on a
run's rPr; a:buFont, a:sym on a paragraph's pPr) declare an Overpass-family typeface, broken
down by exact typeface name and by element tag, plus the Red Hat Mono element count (which
must not change) and a sample of shapes that will be touched. With --apply, rewrites every
matching element's typeface to "Red Hat Display", backs up the original deck to
$DECK_BACKUP_DIR (default ~/.cache/deck_edit/backup, same convention as deck_edit.py) and
saves in place (or to --out).

A typeface attribute value can never simultaneously read "Overpass..." and a mono family
(Red Hat Mono, Courier, ...), so matching on the Overpass regex alone can never touch a
code/mono element -- there is no need to separately exclude code boxes. All five font-carrying
tags are covered because PowerPoint declares a run's font three times (a:latin, a:ea, a:cs,
all children of a:rPr) and a paragraph's bullet-glyph font twice more (a:buFont, a:sym,
children of a:pPr) -- leaving any of the five unchanged would leave the raw string "Overpass"
in the slide XML even though no visible run looks unconverted.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pptx import Presentation  # noqa: E402

import deck_edit as de  # noqa: E402

A, P = de.A, de.P
MONO_RE = de.MONO_RE
OVERPASS_RE = re.compile(r"overpass", re.I)
TARGET = "Red Hat Display"
FONT_TAGS = ("latin", "ea", "cs", "buFont", "sym")


def q(ns, tag):
    return de.q(ns, tag)


def all_font_elements(prs):
    """Every a:latin / a:ea / a:cs / a:buFont / a:sym element in the whole deck: slide shapes
    (including grouped/table cells, via the slide root's own .iter()) and notes bodies. Mirrors
    deck_edit's "both" scope. Yields (slide_id, "slide"|"notes", tag, element)."""
    for s in prs.slides:
        for tag in FONT_TAGS:
            for el in s._element.iter(q(A, tag)):
                yield s.slide_id, "slide", tag, el
        for nr in de.notes_roots(s):
            for tag in FONT_TAGS:
                for el in nr.iter(q(A, tag)):
                    yield s.slide_id, "notes", tag, el


def report(prs):
    counts = Counter()
    by_tag = Counter()
    mono_count = 0
    samples = []
    for sid, kind, tag, el in all_font_elements(prs):
        tf = el.get("typeface") or ""
        if MONO_RE.search(tf):
            mono_count += 1
            continue
        if OVERPASS_RE.search(tf):
            counts[tf] += 1
            by_tag[tag] += 1
            if len(samples) < 8:
                # a:latin/a:ea/a:cs hang off a run's rPr (sibling a:t holds the text); a:buFont/
                # a:sym hang off a paragraph's pPr (the whole a:p holds the text) -- walk up to
                # the run or paragraph for a readable sample.
                holder = el.getparent()
                while holder is not None and holder.tag not in (q(A, "r"), q(A, "p")):
                    holder = holder.getparent()
                text = "".join(holder.itertext())[:50] if holder is not None else ""
                samples.append((sid, kind, tag, tf, text))
    print("Overpass-family font elements by exact typeface:")
    total = 0
    for font, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d}  {font!r}")
        total += n
    print(f"  {total:5d}  TOTAL -> would become {TARGET!r}")
    print("\nBy element tag:")
    for tag, n in sorted(by_tag.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d}  a:{tag}")
    print(f"\nRed Hat Mono (or other mono-family) font elements, same 5 tags (must be unaffected): {mono_count}")
    print("\nSample elements to be changed:")
    for sid, kind, tag, tf, text in samples:
        print(f"  sldId {sid} [{kind}] a:{tag} {tf!r}: {text!r}")
    return total, mono_count


def apply(prs):
    changed = 0
    for sid, kind, tag, el in all_font_elements(prs):
        tf = el.get("typeface") or ""
        if MONO_RE.search(tf):
            continue
        if OVERPASS_RE.search(tf):
            el.set("typeface", TARGET)
            changed += 1
    return changed


def backup_dir():
    return Path(os.environ.get("DECK_BACKUP_DIR") or Path.home() / ".cache" / "deck_edit" / "backup")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("deck", type=Path)
    ap.add_argument("--apply", action="store_true", help="rewrite the deck (default: report only)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    prs = Presentation(str(args.deck))

    if not args.apply:
        total, mono_count = report(prs)
        print(f"\n(report only; re-run with --apply to retarget {total} run(s) to {TARGET!r})")
        return 0

    def mono_count():
        return sum(1 for _, _, _, el in all_font_elements(prs) if MONO_RE.search(el.get("typeface") or ""))

    before_mono = mono_count()
    changed = apply(prs)
    after_mono = mono_count()
    if after_mono != before_mono:
        print(f"deck_font: ABORTED, nothing written: mono font-element count changed {before_mono} -> {after_mono}",
              file=sys.stderr)
        return 1

    target = args.out or args.deck
    tmpdir = Path(tempfile.mkdtemp(prefix="deck_font_"))
    tmp = tmpdir / target.name
    try:
        prs.save(str(tmp))
        Presentation(str(tmp))  # reload check
        if args.out is None:
            bdir = backup_dir()
            bdir.mkdir(parents=True, exist_ok=True)
            b = bdir / f"{args.deck.stem}.{time.strftime('%Y%m%d-%H%M%S')}{args.deck.suffix}"
            shutil.copy2(args.deck, b)
            print(f"backup: {b}")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, target) if tmp.stat().st_dev == target.parent.stat().st_dev else shutil.move(str(tmp), str(target))
        print(f"deck_font: retargeted {changed} font element(s) to {TARGET!r} (mono elements unaffected: {after_mono})")
        print(f"out: {target}")
        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
