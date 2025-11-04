
#!/usr/bin/env python3
"""
fix_affinity_svg.py

Purpose
-------
Affinity (and some other DTP apps) often export multi-line text in metadata-like fields
with literal "\n" sequences. SVG collapses whitespace, so "\n" is *not* treated as a line
break in most renderers—resulting in visible "\n" or misaligned text.

This script post-processes an SVG to:
  1) Find <text> nodes whose *direct text* or child <tspan> content contains the 2-character
     backslash-n sequence ("\n").
  2) Replace those "\n" sequences with proper <tspan> line runs, using 'dy' increments based on
     the element's font-size (defaulting to 1.2 * font-size as a crude line-height if none found).
  3) Add xml:space="preserve" to the <text> element to keep leading/trailing spaces.
  4) Optionally, strip any 'white-space' CSS on the element that would fight line breaks.
     (We only remove 'white-space' if set directly on the element's 'style' attribute.)

Usage
-----
python fix_affinity_svg.py input.svg output.svg

Notes
-----
- We do *not* flatten transforms. The new tspans inherit the original transform chain.
- We keep the element's x/y as-is. Each new <tspan> gets 'x' equal to the parent <text>'s
  first x (if present); otherwise it relies on normal text positioning.
- If the element already has tspans, we only rebuild the ones that contain "\n".
- Back up your file first.
"""
import sys
import re
from copy import deepcopy
from lxml import etree

NS = {"svg": "http://www.w3.org/2000/svg"}

def parse_font_size(style_attr: str):
    """Return font-size in px (float) if present in a style string; else None."""
    if not style_attr:
        return None
    m = re.search(r'font-size\s*:\s*([0-9.]+)px', style_attr)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None

def get_text_x(element):
    """Return the first x of a <text> element if present, else None."""
    x = element.get("x")
    if x:
        # x can be a list of numbers; take the first
        parts = x.strip().split()
        if parts:
            return parts[0]
    return None

def clean_white_space_in_style(style_attr: str):
    """Remove any 'white-space: ...' from the style string to avoid conflicts."""
    if not style_attr:
        return style_attr
    # remove any white-space: ...; occurrences (conservative)
    new_style = re.sub(r'white-space\s*:\s*[^;]+;?', '', style_attr)
    # collapse double semicolons
    new_style = re.sub(r';{2,}', ';', new_style).strip()
    # strip leading/trailing semicolons
    new_style = new_style.strip('; ')
    return new_style

def split_into_tspans(el, text, base_x, line_height_px):
    """
    Replace el's text content with a series of <tspan> children for each line.
    First line uses dy=0; subsequent lines use dy=line_height_px.
    """
    lines = text.split("\\n")
    # Clear direct text and children
    el.text = None
    # Build tspans
    for i, line in enumerate(lines):
        tspan = etree.Element("tspan")
        if base_x is not None:
            tspan.set("x", base_x)
        if i > 0:
            # dy: line height
            tspan.set("dy", f"{line_height_px}px")
        tspan.text = line
        el.append(tspan)

def process_text_node(text_el):
    style_attr = text_el.get("style")
    font_size = parse_font_size(style_attr) or parse_font_size(text_el.get("style"))
    # Fallback line height multiplier
    line_height = (font_size or 12.0) * 1.2
    base_x = get_text_x(text_el)

    # Ensure xml:space="preserve"
    text_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    # Clean white-space CSS if present on the same element
    if style_attr and "white-space" in style_attr:
        cleaned = clean_white_space_in_style(style_attr)
        if cleaned != style_attr:
            text_el.set("style", cleaned)

    # If direct text contains "\n", split it
    if text_el.text and "\\n" in text_el.text:
        split_into_tspans(text_el, text_el.text, base_x, line_height)
        return True

    # Otherwise, scan child tspans and fix any that contain "\n"
    changed_any = False
    for child in list(text_el):
        if child.tag.endswith("tspan") and child.text and "\\n" in child.text:
            # Insert new tspans at the same position as child
            idx = list(text_el).index(child)
            lines = child.text.split("\\n")
            dy_first = child.get("dy")
            x_child = child.get("x") or base_x
            # Remove the old child
            text_el.remove(child)
            # Rebuild
            for j, line in enumerate(lines):
                tspan = etree.Element("tspan")
                if x_child is not None:
                    tspan.set("x", x_child)
                if j == 0:
                    # keep original dy for first line if existed
                    if dy_first:
                        tspan.set("dy", dy_first)
                else:
                    tspan.set("dy", f"{(parse_font_size(child.get('style')) or font_size or 12.0) * 1.2}px")
                tspan.text = line
                text_el.insert(idx + j, tspan)
            changed_any = True
    return changed_any

def main():
    if len(sys.argv) != 3:
        print("Usage: python fix_affinity_svg.py input.svg output.svg")
        sys.exit(1)
    inp, outp = sys.argv[1], sys.argv[2]
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(inp, parser)
    root = tree.getroot()

    changed = False
    # Find all <text> elements in the SVG namespace or any namespace ending with 'text'
    for text_el in root.xpath('//svg:text', namespaces=NS):
        if process_text_node(text_el):
            changed = True
    # Also handle cases without proper namespace (fallback)
    for text_el in root.findall(".//{*}text"):
        if process_text_node(text_el):
            changed = True

    tree.write(outp, pretty_print=True, xml_declaration=True, encoding="utf-8")
    print("Wrote:", outp)
    if not changed:
        print("Note: no '\\n' sequences found in <text> content. If your newline appears literally on canvas, it may be coming from a symbol, a <foreignObject>, or an embedded image layer rather than a text node.")
if __name__ == "__main__":
    main()
