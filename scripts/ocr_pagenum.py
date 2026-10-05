#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐页确认页码(per-parity 角部裁剪 + 预期值反查)。"""
import os, re, csv, argparse
from PIL import Image, ImageOps
import pytesseract

SRC = r"D:\Downloads\333"
OUT = r"D:\doc_merge\pagenumbers_v3.csv"
W, H = 3072, 4096

def expected(seq):
    return 2 * seq - 1 if seq <= 90 else 2 * (seq - 90)

def ocr_corner(path, box):
    im = Image.open(path)
    crop = im.crop(box).convert("L")
    crop = ImageOps.autocontrast(crop)
    crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
    txt = pytesseract.image_to_string(
        crop, config="--psm 6 -c tessedit_char_whitelist=0123456789").strip()
    return txt

def try_confirm(path, exp):
    """返回 (hit, runs_text)"""
    # 奇数页:右上;偶数页:左上
    if exp % 2 == 1:
        boxes = [(int(W*0.55), 0, W, int(H*0.16))]            # 右上
    else:
        boxes = [(0, 0, int(W*0.45), int(H*0.16))]            # 左上
    for box in boxes:
        txt = ocr_corner(path, box)
        runs = re.findall(r"\d{1,3}", txt)
        ints = [int(r) for r in runs]
        if exp in ints or any(v in txt for v in [str(exp), f"{exp:02d}", f"{exp:03d}"]):
            return True, txt
    return False, ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    files = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".jpg"))
    if args.limit:
        files = files[:args.limit]
    rows = []; confirmed = 0
    for i, fn in enumerate(files, 1):
        exp = expected(i)
        hit, txt = try_confirm(os.path.join(SRC, fn), exp)
        note = "CONFIRMED" if hit else "CHECK:" + txt.replace("\n", " ")
        if hit:
            confirmed += 1
        rows.append({"seq": i, "file": fn, "expected": exp, "ok": note})
        print(f"[{i:3}] {fn}  exp={exp}  {note}", flush=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["seq", "file", "expected", "ok"])
        w.writeheader(); w.writerows(rows)
    print(f"\n==== 确认 {confirmed}/{len(files)} ====")

if __name__ == "__main__":
    main()
