#!/usr/bin/env python3
"""
Update text by element ID in an SVG exported from Affinity Designer.

Usage:
  python update_svg_text.py path/to/file.svg \
      --title "Grappa di Moscato" \
      --description "Distillata con cura. 42% vol, lotto 23-09."

Notes:
- Works whether the text is in <text> directly or inside <tspan>s.
- Leaves all other content unchanged.
- Writes a timestamped backup next to the input file before saving.
"""

import argparse
import datetime as _dt
import shutil
import sys
from pathlib import Path

# Prefer built-in ElementTree; you can switch to lxml.etree if installed.
USE_LXML = False
try:
    import lxml.etree as ET  # type: ignore
    USE_LXML = True
except ImportError:
    import xml.etree.ElementTree as ET  # type: ignore


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
NSMAP = {"svg": SVG_NS, "xlink": XLINK_NS}

def localname(tag):
    return tag.split("}")[-1] if "}" in tag else tag

def _register_namespaces():
    # Ensures namespaces are preserved on write
    try:
        ET.register_namespace("", SVG_NS)
        ET.register_namespace("xlink", XLINK_NS)
    except Exception:
        pass


def _find_by_id(root, elem_id):
    """
    Find any element with the given id, regardless of tag/namespace.
    """
    # XPath works with both ET and lxml as long as we pass namespaces when needed.
    # .//*[@id='Title']
    return root.find(f".//*[@id='{elem_id}']")


def _find_text_or_tspan_descendant(elem):
    # Depth-first search: return the first descendant that is a <text> or <tspan>
    stack = list(elem)
    while stack:
        node = stack.pop(0)
        ln = localname(node.tag)
        if ln in ("text", "tspan"):
            return node
        # enqueue children
        stack[0:0] = list(node)
    return None

# Helper to clear .text and all child tspan texts for every descendant <text>/<tspan>
def _clear_all_text_descendants(elem, except_node=None):
    """Clear .text and all child tspan texts for every descendant <text>/<tspan>
    except the provided node. Also clears .tail on children to avoid stray spaces."""
    def ln(tag):
        return tag.split('}')[-1] if '}' in tag else tag
    stack = list(elem)
    while stack:
        node = stack.pop(0)
        if node is except_node:
            stack[0:0] = list(node)
            continue
        if ln(node.tag) in ("text", "tspan"):
            node.text = ""
            # clear tspans if any
            for ch in list(node):
                ch.text = ""
                ch.tail = ""
            node.tail = ""
        # enqueue children
        stack[0:0] = list(node)


def _set_text(elem, value: str):
    """
    Set the visible text of an SVG text node (or tspan).
    Handles:
      - <text> with no children: elem.text = value
      - <text> with <tspan>s: put value in first tspan, strip others' text
      - If the selected element itself is a <tspan>, set that tspan's text.
    Multi-line support:
      - If your value contains '\n' and the node already has multiple <tspan>s,
        lines will be distributed across existing tspans. Otherwise, the value
        goes into a single node (no new tspans created).
    """
    tag = localname(elem.tag)

    if tag == "g":
        # Some exporters (Affinity) assign IDs to groups; find a nested text/tspan.
        original_group = elem  # keep a reference before reassigning
        target = _find_text_or_tspan_descendant(elem)
        if target is None:
            # Nothing to set inside this group
            return
        # Clear any other text/tspan nodes inside the group so we don't append visually
        _clear_all_text_descendants(original_group, except_node=target)
        elem = target
        tag = localname(elem.tag)

    # Helper to clear text of all children tspans
    def _children_tspans(e):
        return [c for c in list(e) if localname(c.tag) == "tspan"]

    # If the element itself is a tspan
    if tag == "tspan":
        _apply_value_to_node(elem, value)
        return

    # If the element is a text node
    if tag == "text":
        tspans = _children_tspans(elem)
        if not tspans:
            # Simple case: no tspans, just write text
            elem.text = value
        else:
            # If value has multiple lines and there are multiple tspans,
            # distribute across existing tspans; extra tspans get blanked.
            lines = value.split("\n")
            for i, tspan in enumerate(tspans):
                _apply_value_to_node(tspan, lines[i] if i < len(lines) else "")
            # Also clear any direct .text on <text> (to avoid stray text)
            elem.text = None
            # Clear any tspan.tail to avoid prefixed spaces
            for tspan in tspans:
                tspan.tail = ""
        return

    # If some other element accidentally has the ID, try to set .text anyway
    elem.text = value


def _apply_value_to_node(node, value: str):
    """
    Safely write text to a node that may already have .text and children.
    Keeps children structure but clears any existing text content and tails
    to avoid stray whitespace from the original export.
    """
    node.text = value
    for child in list(node):
        child.text = ""
        child.tail = ""
    node.tail = ""


def set_text_by_id(root, field_id: str, value: str) -> bool:
    elem = _find_by_id(root, field_id)
    if elem is None:
        return False
    _set_text(elem, value)
    return True


def backup_file(path: Path) -> Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(f".backup-{stamp}.svg")
    shutil.copy2(path, backup)
    return backup


def main():
    _register_namespaces()

    ap = argparse.ArgumentParser(description="Update SVG text fields by ID.")
    ap.add_argument("svg_path", type=Path, help="Path to the SVG file exported from Affinity")
    ap.add_argument("--title", help="New text for element with id='TITLE'")
    ap.add_argument("--description", help="New text for element with id='DESCRIPTION'")
    ap.add_argument("--out", type=Path, default=None,
                    help="Optional output path. If omitted, overwrites the input (after backup).")
    args = ap.parse_args()

    if not args.svg_path.exists():
        print(f"ERROR: {args.svg_path} not found.", file=sys.stderr)
        sys.exit(1)

    if not (args.title or args.description):
        print("Nothing to do: provide --title and/or --description.", file=sys.stderr)
        sys.exit(1)

    # Parse
    try:
        tree = ET.parse(str(args.svg_path))
        root = tree.getroot()
    except Exception as e:
        print(f"ERROR parsing SVG: {e}", file=sys.stderr)
        sys.exit(1)

    # Update fields
    updated_any = False
    if args.title is not None:
        updated_any |= set_text_by_id(root, "TITLE", args.title)
    if args.description is not None:
        updated_any |= set_text_by_id(root, "DESCRIPTION", args.description)

    if not updated_any:
        print("WARNING: No elements with id='TITLE' or id='DESCRIPTION' were found.", file=sys.stderr)

    # Write output
    out_path = args.out if args.out else args.svg_path
    if args.out is None:
        bkp = backup_file(args.svg_path)
        print(f"Backup written: {bkp.name}")

    try:
        if USE_LXML:
            # Pretty print if lxml is available
            tree.write(str(out_path), encoding="utf-8", xml_declaration=True, pretty_print=True)
        else:
            tree.write(str(out_path), encoding="utf-8", xml_declaration=True)
        print(f"Saved: {out_path}")
    except Exception as e:
        print(f"ERROR writing output: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
