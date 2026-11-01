#!/usr/bin/env python3
"""Inject Red Hat brand fonts into a pristine .pptx deck by harvesting
EOT ``.fntdata`` parts out of a LibreOffice-embedded THROWAWAY copy of the
SAME deck, and hand-wiring them into the pristine file -- without ever
opening the pristine file in LibreOffice and without touching any
slide/theme/master XML or shape IDs.

Why this exists
----------------
A direct LibreOffice round-trip save of these decks is lossy: it bloats
the file (embeds megabytes of unwanted Noto CJK/Devanagari fallback font
data), renumbers every shape ID, and rewrites the theme. But LibreOffice
*does* produce correct, correctly-subset EOT ``.fntdata`` for the Red Hat
families actually used in a deck. So the method is:

    1. Run ``deck_embed_fonts.py`` (LibreOffice/UNO) on a THROWAWAY COPY
       of the deck to produce the EOT font data.
    2. Harvest only the Red Hat ``.fntdata`` parts from that throwaway,
       using the throwaway's own ``ppt/presentation.xml`` +
       ``ppt/_rels/presentation.xml.rels`` as the map of which font
       family/style slots (regular/bold/italic/boldItalic) were actually
       embedded -- this already reflects LibreOffice's "only embed used
       glyphs" decision, including cases where a style slot (e.g.
       boldItalic) is synthesized from another slot's font data.
    3. Hand-inject those parts into the PRISTINE committed .pptx via
       zip + targeted string surgery on exactly three parts:
           - ``[Content_Types].xml``           (fntdata Default)
           - ``ppt/_rels/presentation.xml.rels`` (font Relationships)
           - ``ppt/presentation.xml``            (embedTrueTypeFonts +
                                                   <p:embeddedFontLst>)
       Every other part (every slide, every theme, every slideMaster/
       slideLayout, notesSlides, etc.) is copied byte-for-byte from the
       pristine zip, so shape IDs and all other XML are untouched.

Reference structure: the CNDP deck
(cloud-native-design-patterns/lgtm-presentation/
Designing-Cloud-Native-APIs-Python.pptx) was used to confirm the exact
expected wiring: a ``fntdata`` Default Extension in [Content_Types].xml
(not per-part Overrides), one font Relationship per embedded part in
presentation.xml.rels, and a ``<p:embeddedFontLst>`` placed immediately
after ``<p:notesSz .../>`` in presentation.xml, with
``embedTrueTypeFonts="1"`` on the ``<p:presentation>`` root.

Usage
-----
    # 1. Make a throwaway copy and LO-embed it (system python3, not
    #    .venv-decks -- needs the `uno` bindings LibreOffice ships):
    cp presentation/lgtm-presentation/Modernizing-101.pptx /tmp/throwaway.pptx
    python3 scripts/deck_embed_fonts.py /tmp/throwaway.pptx

    # 2. Inject the harvested Red Hat fonts into the real, pristine deck
    #    (any python3 works for this step -- pure stdlib zipfile/re):
    python3 scripts/deck_inject_fonts.py \\
        presentation/lgtm-presentation/Modernizing-101.pptx /tmp/throwaway.pptx

The pristine deck is overwritten in place only after the rebuilt zip is
verified to open and contain the expected parts. Pass ``--output`` to
write elsewhere instead of overwriting in place. Pass ``--dry-run`` to
print what would be done without writing anything.

This script is idempotent/rerunnable: if the pristine deck already has a
previous Red Hat font injection (e.g. after a future content edit changed
which glyphs are used and you re-ran step 1), it strips the old
``ppt/fonts/RedHat*.fntdata`` parts, old font Relationships, and the old
``<p:embeddedFontLst>`` before re-injecting the freshly harvested set.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
FONT_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"

# Only these families get embedded -- Noto CJK/Devanagari fallback and any
# other LibreOffice-added family (Overpass, +mn-lt placeholders, etc.) are
# discarded even if present in the throwaway.
FAMILY_SLUG = {
    "Red Hat Display": "RedHatDisplay",
    "Red Hat Text": "RedHatText",
    "Red Hat Mono": "RedHatMono",
}
FAMILY_ORDER = ["Red Hat Display", "Red Hat Text", "Red Hat Mono"]
STYLE_TAGS = ["regular", "bold", "italic", "boldItalic"]


class InjectError(RuntimeError):
    pass


def harvest_red_hat_fonts(throwaway_path: Path) -> list[tuple[str, dict[str, bytes]]]:
    """Read the LO-embedded throwaway deck and return
    [(family, {style: fntdata_bytes})] for Red Hat families only, using the
    throwaway's own presentation.xml + rels as the authoritative map of
    which style slots were actually embedded."""
    with zipfile.ZipFile(throwaway_path) as zf:
        try:
            pres_xml = zf.read("ppt/presentation.xml")
            rels_xml = zf.read("ppt/_rels/presentation.xml.rels")
        except KeyError as exc:
            raise InjectError(
                f"{throwaway_path} is missing ppt/presentation.xml or its "
                "rels -- did deck_embed_fonts.py run on it?"
            ) from exc

        rels_root = ET.fromstring(rels_xml)
        rid_to_target: dict[str, str] = {}
        for rel in rels_root:
            if rel.get("Type") == FONT_REL_TYPE:
                rid_to_target[rel.get("Id")] = rel.get("Target")

        pres_root = ET.fromstring(pres_xml)
        lst = pres_root.find(f"{{{P_NS}}}embeddedFontLst")
        if lst is None:
            raise InjectError(
                f"{throwaway_path} has no <p:embeddedFontLst> -- "
                "LibreOffice did not embed any fonts (run deck_embed_fonts.py first)"
            )

        families: list[tuple[str, dict[str, bytes]]] = []
        for ef in lst.findall(f"{{{P_NS}}}embeddedFont"):
            font_el = ef.find(f"{{{P_NS}}}font")
            typeface = font_el.get("typeface") if font_el is not None else None
            if typeface not in FAMILY_SLUG:
                continue  # Noto fallback / +mn-lt placeholder / non-Red-Hat family
            styles: dict[str, bytes] = {}
            for style in STYLE_TAGS:
                el = ef.find(f"{{{P_NS}}}{style}")
                if el is None:
                    continue
                rid = el.get(f"{{{R_NS}}}id")
                target = rid_to_target.get(rid)
                if not target:
                    continue
                part_name = "ppt/" + target
                try:
                    styles[style] = zf.read(part_name)
                except KeyError:
                    continue
            if styles:
                families.append((typeface, styles))
        return families


def dedupe_and_name(
    families: list[tuple[str, dict[str, bytes]]]
) -> tuple[list[tuple[str, str, str]], dict[str, bytes]]:
    """Collapse identical font-data blobs (e.g. LibreOffice reusing the
    italic file for boldItalic when no distinct boldItalic glyph set is
    used) onto a single ppt/fonts/<Name>-<style>.fntdata part, named after
    the first style that needs it. Returns:
        entries: [(family, style, filename)]  -- one row per style slot
        files:   {filename: bytes}             -- one row per unique blob
    """
    by_family: dict[str, dict[str, bytes]] = {}
    for family, styles in families:
        by_family.setdefault(family, {}).update(styles)

    hash_to_filename: dict[str, str] = {}
    files: dict[str, bytes] = {}
    entries: list[tuple[str, str, str]] = []

    for family in FAMILY_ORDER:
        styles = by_family.get(family)
        if not styles:
            continue
        slug = FAMILY_SLUG[family]
        for style in STYLE_TAGS:
            data = styles.get(style)
            if data is None:
                continue
            digest = hashlib.sha256(data).hexdigest()
            filename = hash_to_filename.get(digest)
            if filename is None:
                filename = f"{slug}-{style}.fntdata"
                hash_to_filename[digest] = filename
                files[filename] = data
            entries.append((family, style, filename))
    return entries, files


def strip_previous_injection(content_types: str, rels: str, presentation: str) -> tuple[str, str, str]:
    """Make re-running this script idempotent: remove any Red-Hat font
    relationships, embeddedFontLst, and (the caller separately drops the
    ppt/fonts/RedHat*.fntdata parts) left by an earlier injection."""
    rels = re.sub(
        r'<Relationship\b[^>]*Target="fonts/RedHat[^"]*\.fntdata"[^>]*/>',
        "",
        rels,
    )
    presentation = re.sub(
        r"<p:embeddedFontLst>.*?</p:embeddedFontLst>",
        "",
        presentation,
        flags=re.DOTALL,
    )
    return content_types, rels, presentation


def next_rids(rels: str, count: int) -> list[str]:
    existing = [int(n) for n in re.findall(r'Id="rId(\d+)"', rels)]
    start = (max(existing) + 1) if existing else 1
    return [f"rId{start + i}" for i in range(count)]


def ensure_fntdata_content_type(content_types: str) -> str:
    if re.search(r'<Default\s+Extension="fntdata"', content_types):
        return content_types
    return re.sub(
        r"(<Types\b[^>]*>)",
        r'\1<Default Extension="fntdata" ContentType="application/x-fontdata"/>',
        content_types,
        count=1,
    )


def add_font_relationships(rels: str, filename_to_rid: dict[str, str]) -> str:
    new_rels = "".join(
        f'<Relationship Id="{rid}" Type="{FONT_REL_TYPE}" Target="fonts/{filename}"/>'
        for filename, rid in filename_to_rid.items()
    )
    if "</Relationships>" not in rels:
        raise InjectError("presentation.xml.rels has no </Relationships> closing tag")
    return rels.replace("</Relationships>", new_rels + "</Relationships>", 1)


def set_embed_true_type_fonts(presentation: str) -> str:
    def fix_tag(m: re.Match) -> str:
        attrs = m.group(1)
        if "embedTrueTypeFonts=" in attrs:
            attrs = re.sub(r'embedTrueTypeFonts="[^"]*"', 'embedTrueTypeFonts="1"', attrs)
        else:
            attrs = attrs + ' embedTrueTypeFonts="1"'
        return f"<p:presentation{attrs}>"

    new_text, n = re.subn(r"<p:presentation([^>]*)>", fix_tag, presentation, count=1)
    if n == 0:
        raise InjectError("could not find <p:presentation ...> root element")
    return new_text


def build_embedded_font_lst(entries: list[tuple[str, str, str]], filename_to_rid: dict[str, str]) -> str:
    by_family: dict[str, dict[str, str]] = {}
    for family, style, filename in entries:
        by_family.setdefault(family, {})[style] = filename_to_rid[filename]

    parts = ["<p:embeddedFontLst>"]
    for family in FAMILY_ORDER:
        styles = by_family.get(family)
        if not styles:
            continue
        parts.append(f'<p:embeddedFont><p:font typeface="{family}"/>')
        for style in STYLE_TAGS:
            rid = styles.get(style)
            if rid is None:
                continue
            parts.append(f'<p:{style} r:id="{rid}"/>')
        parts.append("</p:embeddedFont>")
    parts.append("</p:embeddedFontLst>")
    return "".join(parts)


def insert_embedded_font_lst(presentation: str, lst_xml: str) -> str:
    pattern = r"(<p:notesSz\b[^>]*/>)"
    new_text, n = re.subn(pattern, lambda m: m.group(1) + lst_xml, presentation, count=1)
    if n == 0:
        raise InjectError("could not find <p:notesSz .../> to anchor <p:embeddedFontLst> after")
    return new_text


def inject(pristine_path: Path, throwaway_path: Path, output_path: Path, dry_run: bool = False) -> dict:
    families = harvest_red_hat_fonts(throwaway_path)
    if not families:
        raise InjectError(f"no Red Hat fonts found embedded in {throwaway_path}")
    entries, files = dedupe_and_name(families)

    report = {
        "families": sorted({f for f, _, _ in entries}),
        "parts": {name: len(data) for name, data in files.items()},
    }

    with zipfile.ZipFile(pristine_path) as zf:
        infolist = zf.infolist()
        content_types = zf.read("[Content_Types].xml").decode("utf-8")
        rels = zf.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        presentation = zf.read("ppt/presentation.xml").decode("utf-8")
        original_bytes = {
            info.filename: zf.read(info.filename)
            for info in infolist
            if info.filename
            not in ("[Content_Types].xml", "ppt/_rels/presentation.xml.rels", "ppt/presentation.xml")
            and not info.filename.startswith("ppt/fonts/RedHat")
        }

    content_types, rels, presentation = strip_previous_injection(content_types, rels, presentation)

    content_types = ensure_fntdata_content_type(content_types)

    filenames = list(files.keys())
    rids = next_rids(rels, len(filenames))
    filename_to_rid = dict(zip(filenames, rids))

    rels = add_font_relationships(rels, filename_to_rid)

    presentation = set_embed_true_type_fonts(presentation)
    lst_xml = build_embedded_font_lst(entries, filename_to_rid)
    presentation = insert_embedded_font_lst(presentation, lst_xml)

    report["embed_true_type_fonts"] = 'embedTrueTypeFonts="1"' in presentation
    report["embedded_font_lst"] = lst_xml
    report["relationships_added"] = filename_to_rid

    if dry_run:
        return report

    with zipfile.ZipFile(pristine_path) as zf:
        infolist_by_name = {info.filename: info for info in zf.infolist()}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in original_bytes.items():
            info = infolist_by_name[name]
            out.writestr(info, data)
        # Overwrite the three modified parts (reuse original ZipInfo where
        # we have one, i.e. always -- these three parts always exist).
        out.writestr(infolist_by_name["[Content_Types].xml"], content_types.encode("utf-8"))
        out.writestr(
            infolist_by_name["ppt/_rels/presentation.xml.rels"], rels.encode("utf-8")
        )
        out.writestr(infolist_by_name["ppt/presentation.xml"], presentation.encode("utf-8"))
        for filename, data in files.items():
            out.writestr(f"ppt/fonts/{filename}", data)

    if not zipfile.is_zipfile(tmp_path):
        tmp_path.unlink(missing_ok=True)
        raise InjectError("rebuilt pptx failed basic zip validation")

    tmp_path.replace(output_path)
    report["output"] = str(output_path)
    return report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pristine", type=Path, help="committed .pptx to inject fonts into")
    ap.add_argument("throwaway", type=Path, help="LO-font-embedded throwaway copy of the SAME deck")
    ap.add_argument("--output", type=Path, default=None, help="write here instead of overwriting pristine")
    ap.add_argument("--dry-run", action="store_true", help="report what would happen; write nothing")
    args = ap.parse_args(argv)

    output_path = args.output or args.pristine
    try:
        report = inject(args.pristine, args.throwaway, output_path, dry_run=args.dry_run)
    except InjectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"families embedded: {', '.join(report['families'])}")
    for name, size in report["parts"].items():
        print(f"  ppt/fonts/{name}  ({size:,} bytes)")
    print(f"embedTrueTypeFonts set: {report['embed_true_type_fonts']}")
    if args.dry_run:
        print("(dry run -- nothing written)")
    else:
        print(f"wrote: {report['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
