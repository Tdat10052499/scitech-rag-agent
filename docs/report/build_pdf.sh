#!/usr/bin/env bash
# Build the report PDF from the Markdown chapters of this folder (task W8-D4-LDN-1).
#
#   bash docs/report/build_pdf.sh            # writes docs/report/build/ASAP-RAG-Agent-report.pdf
#
# Needs: pandoc (3.x) and a TeX Live with xelatex (packages: fontspec, fvextra, xurl, etoolbox,
# fancyhdr, float, booktabs, longtable, graphicx, hyperref, xcolor). Nothing is installed or
# downloaded by this script, and the Markdown files are not changed: it works on a copy in build/.
#
# Fonts: Times New Roman 12 pt body with line spacing 1.5 (if the font is missing, Liberation Serif or
# TeX Gyre Termes is used); code in DejaVu Sans Mono. Override: MAINFONT="..." MONOFONT="Consolas" bash ...
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$HERE/build"
OUT="$BUILD/ASAP-RAG-Agent-report.pdf"
MAINFONT="${MAINFONT:-}"   # default: Times New Roman, else Liberation Serif (pdf/header.tex)
MONOFONT="${MONOFONT:-DejaVu Sans Mono}"

for tool in pandoc xelatex; do
  command -v "$tool" >/dev/null || { echo "error: $tool is not installed" >&2; exit 1; }
done

rm -rf "$BUILD"
mkdir -p "$BUILD"
cp -r "$HERE/figures" "$BUILD/figures"

# The cover is a LaTeX page (pdf/cover.tex, with its images in pdf/cover/); the contents page follows it.
mkdir -p "$BUILD/cover"
cp "$HERE"/pdf/cover/*.png "$BUILD/cover/"
{ printf '```{=latex}\n'; cat "$HERE/pdf/cover.tex"; printf '\n```\n\n'; } > "$BUILD/00-cover.md"
printf '\n\\tableofcontents\n\\clearpage\n' > "$BUILD/00-toc.md"

FILES=("$BUILD/00-cover.md" "$BUILD/00-toc.md")
for f in 01-introduction 02-data 03-system 04-evaluation 05-interface 06-conclusion 07-appendix 08-references; do
  cp "$HERE/$f.md" "$BUILD/$f.md"
  FILES+=("$BUILD/$f.md")
done

( cd "$BUILD" && pandoc "${FILES[@]}" \
    --from markdown-implicit_figures \
    --pdf-engine=xelatex \
    --lua-filter="$HERE/pdf/filter.lua" \
    --include-in-header="$HERE/pdf/header.tex" \
    -V fontfamily=fontspec \
    ${MAINFONT:+-V mainfont="$MAINFONT"} -V monofont="$MONOFONT" -V monofontoptions=Scale=0.85 \
    -V documentclass=article -V classoption=a4paper -V fontsize=12pt \
    -V geometry:margin=2.2cm -V colorlinks=true -V linkcolor=black -V urlcolor=blue \
    -V title="" \
    --resource-path="$BUILD" \
    -o "$OUT" )

echo "wrote $OUT"
