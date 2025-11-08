#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./convert-eps-to-svg.sh /path/to/input [/path/to/output]
# Defaults: output goes to "<input>/SVG"

if ! command -v /Applications/Inkscape.app/Contents/MacOS/inkscape >/dev/null 2>&1; then
  echo "Error: inkscape not found in PATH." >&2
  exit 1
fi

SRC="${1:-.}"
OUT="${2:-$SRC/SVG}"

mkdir -p "$OUT"

# Find all EPS files recursively (case-insensitive)
# Preserves subfolder structure under OUT
find "$SRC" -type f \( -iname "*.eps" \) | while IFS= read -r file; do
  rel="${file#$SRC/}"                        # path relative to SRC
  rel_noext="${rel%.*}"                      # strip .eps
  outdir="$OUT/$(dirname "$rel_noext")"
  outfile="$OUT/${rel_noext}.svg"

  mkdir -p "$outdir"

  echo "[...] $rel → ${outfile#$OUT/}"

  # Inkscape 1.x syntax:
  # --export-plain-svg makes a cleaner SVG; add --export-text-to-path if you want curves
  /Applications/Inkscape.app/Contents/MacOS/inkscape`` "$file" \
    --export-filename="$outfile" \
    --export-plain-svg \
    >/dev/null

  # Uncomment the next line if you want to convert all text to outlines (curves):
  # inkscape "$outfile" --select-all --verb=ObjectToPath --verb=FileSave --verb=FileClose
  # (If verbs aren’t available in your build, use: inkscape "$file" --export-filename="$outfile" --export-plain-svg --export-text-to-path)
  echo "[OK]  ${outfile#$OUT/}"
done

echo "Done."
