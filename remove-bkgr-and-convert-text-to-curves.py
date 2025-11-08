import os
import re
import argparse
import subprocess
import tempfile
import shutil
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

def which_inkscape():
    p = shutil.which("inkscape")
    if p:
        return p
    mac = "/Applications/Inkscape.app/Contents/MacOS/inkscape"
    if os.path.exists(mac):
        return mac
    return None

def is_white(color: str) -> bool:
    if not color:
        return False
    c = color.strip().lower()
    if c in ("#fff", "#ffffff", "white"):
        return True
    return bool(re.fullmatch(r"rgb\(\s*255\s*,\s*255\s*,\s*255\s*\)", c))

def parse_viewbox(vb: str):
    try:
        parts = [float(p) for p in vb.strip().replace(",", " ").split()]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    except Exception:
        pass
    return None

def parse_length(s: str):
    if s is None:
        return None
    s = s.strip().lower()
    m = re.fullmatch(r"([0-9]*\.?[0-9]+)(px)?", s)
    return float(m.group(1)) if m else None

def get_canvas_size(root):
    vb = root.get("viewBox")
    if vb:
        parsed = parse_viewbox(vb)
        if parsed:
            x0, y0, w, h = parsed
            return (x0, y0, w, h, True)
    w = parse_length(root.get("width"))
    h = parse_length(root.get("height"))
    if w is not None and h is not None:
        return (0.0, 0.0, w, h, False)
    return None

def rect_covers_canvas(rect, canvas, tolerance=0.01):
    x0, y0, W, H, _ = canvas
    for attr in ("x","y","width","height"):
        v = rect.get(attr)
        if v and v.strip().endswith("%"):
            return False
    x = float(rect.get("x") or 0.0)
    y = float(rect.get("y") or 0.0)
    w = rect.get("width"); h = rect.get("height")
    if w is None or h is None:
        return False
    try:
        w = float(w); h = float(h)
    except ValueError:
        return False
    def close(a,b): return abs(a-b) <= (tolerance*abs(b) if b else 1e-9)
    return close(x,x0) and close(y,y0) and close(w,W) and close(h,H)

def get_fill(elem):
    fill = elem.get("fill")
    if fill:
        return fill
    style = elem.get("style")
    if style:
        parts = {}
        for kv in style.split(";"):
            if ":" in kv:
                k, v = kv.split(":", 1)
                parts[k.strip()] = v.strip()
        return parts.get("fill")
    return None

def remove_background_rects(tree):
    root = tree.getroot()
    canvas = get_canvas_size(root)
    if not canvas:
        return 0
    removed = 0
    # Build parent map (xml.etree lacks getparent)
    parent_map = {c: p for p in tree.getroot().iter() for c in list(p)}
    # Check rects at any depth
    for rect in root.findall(".//{http://www.w3.org/2000/svg}rect"):
        fill = get_fill(rect)
        if not is_white(fill):
            continue
        if rect_covers_canvas(rect, canvas):
            parent = parent_map.get(rect)
            if parent is not None:
                parent.remove(rect)
                removed += 1
            else:
                rect.set("fill", "none")
                rect.attrib.pop("style", None)
                removed += 1
    return removed

def inkscape_text_to_path(ink, in_svg, out_svg):
    cmd = [
        ink,
        "--export-type=svg",
        "--export-plain-svg",
        "--export-text-to-path",
        f"--export-filename={out_svg}",
        in_svg,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def process_file(path_in, path_out, do_remove_bg=False, do_text_to_path=False, ink=None):
    tmpdir = tempfile.mkdtemp(prefix="svgproc_")
    try:
        stage = path_in
        # Optional: remove white full-canvas background
        if do_remove_bg:
            tree = ET.parse(stage)
            removed = remove_background_rects(tree)
            stage1 = os.path.join(tmpdir, "stage1.svg")
            tree.write(stage1, encoding="utf-8", xml_declaration=True)
            stage = stage1
        # Optional: convert text to paths with Inkscape
        if do_text_to_path:
            if not ink:
                raise RuntimeError("Inkscape not found; install it or omit --text-to-path.")
            stage2 = os.path.join(tmpdir, "stage2.svg")
            inkscape_text_to_path(ink, stage, stage2)
            stage = stage2
        # Final copy
        if stage != path_out:
            shutil.copyfile(stage, path_out)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def main():
    ap = argparse.ArgumentParser(
        description="Batch process SVGs: optionally remove white background and/or convert text to paths."
    )
    ap.add_argument("input_dir")
    ap.add_argument("output_dir")
    ap.add_argument("--inplace", action="store_true", help="Modify files in place")
    ap.add_argument("--remove-bg", action="store_true", help="Remove white full-canvas background rect")
    ap.add_argument("--text-to-path", action="store_true", help="Convert all <text> to curves (requires Inkscape)")
    args = ap.parse_args()

    ink = None
    if args.text_to_path:
        ink = which_inkscape()
        if not ink:
            print("ERROR: Inkscape not found. Install it or omit --text-to-path.")
            return

    in_dir = args.input_dir
    out_dir = args.input_dir if args.inplace else args.output_dir
    os.makedirs(out_dir, exist_ok=True)

    total = ok = 0
    for name in os.listdir(in_dir):
        if not name.lower().endswith(".svg"):
            continue
        total += 1
        src = os.path.join(in_dir, name)
        dst = src if args.inplace else os.path.join(out_dir, name)
        try:
            process_file(
                src, dst,
                do_remove_bg=args.remove_bg,
                do_text_to_path=args.text_to_path,
                ink=ink
            )
            ok += 1
            ops = []
            if args.remove_bg: ops.append("bg-removed")
            if args.text_to_path: ops.append("text→paths")
            suffix = f" ({', '.join(ops)})" if ops else " (copied)"
            print(f"[OK] {name}{suffix}")
        except Exception as e:
            print(f"[FAIL] {name}: {e}")

    print(f"Done. Processed {total} SVGs; successful: {ok}.")

if __name__ == "__main__":
    main()
