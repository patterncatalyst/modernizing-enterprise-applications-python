#!/usr/bin/env bash
#
# deck_render.sh - render slides of a .pptx to PNG for visual inspection.
#
#   scripts/deck_render.sh <deck.pptx> <outdir> [page ...]
#
# soffice (headless) converts the deck to PDF, pdftoppm writes <outdir>/<deck>-<page>.png at 90 dpi
# (all pages, or only the listed 1-based pages). Aborts when the brand fonts are missing, because
# a render with substituted fonts hides overflow:
#   sudo dnf install -y redhat-text-fonts redhat-display-fonts overpass-fonts
# Environment: LO_PROFILE sets the LibreOffice profile directory (default: a per-user cache dir).
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "usage: $0 <deck.pptx> <outdir> [page ...]" >&2
    exit 2
fi

deck=$1
outdir=$2
shift 2
pages=("$@")

if [[ ! -f "$deck" ]]; then
    echo "deck_render: $deck not found" >&2
    exit 2
fi

fonts=$(fc-list 2>/dev/null || true)
missing=()
for f in "Red Hat Text" "Red Hat Display" "Overpass"; do
    if ! grep -qi -- "$f" <<<"$fonts"; then
        missing+=("$f")
    fi
done
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "deck_render: missing brand font(s): ${missing[*]}" >&2
    echo "Install them first: sudo dnf install -y redhat-text-fonts redhat-display-fonts overpass-fonts" >&2
    exit 3
fi

profile=${LO_PROFILE:-${XDG_CACHE_HOME:-$HOME/.cache}/deck_render/lo-profile}
mkdir -p "$profile" "$outdir"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

soffice --headless "-env:UserInstallation=file://$profile" --convert-to pdf --outdir "$tmp" "$deck" >/dev/null
pdf="$tmp/$(basename "${deck%.*}").pdf"
if [[ ! -f "$pdf" ]]; then
    echo "deck_render: soffice produced no PDF for $deck" >&2
    exit 1
fi

base=$(basename "${deck%.*}")
if [[ ${#pages[@]} -eq 0 ]]; then
    pdftoppm -png -r 90 "$pdf" "$outdir/$base"
else
    for n in "${pages[@]}"; do
        pdftoppm -png -r 90 -f "$n" -l "$n" "$pdf" "$outdir/$base"
    done
fi
echo "deck_render: wrote PNGs for $base in $outdir"
