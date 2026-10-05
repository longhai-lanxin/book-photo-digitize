#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图书电子化全流水线
==================
1. 透视矫正 + 去黑边 + 增强(调用 process_pages 的算法)
2. 在矫正后的页眉区 OCR 读出真实页码,与扫描顺序公式交叉验证
3. 按真实页码命名为 page_001.jpg ... page_180.jpg 输出
4. 记录映射与可疑页,并可合成 PDF

扫描顺序公式(已用样图多次验证):
  文件 1-90 : 奇数页, 页码 = 2*seq - 1
  文件 91-180: 偶数页, 页码 = 2*(seq-90)
"""
import os, re, csv, argparse, importlib.util
from PIL import Image, ImageOps
import pytesseract
import cv2
import numpy as np

# 复用 process_pages 的函数
_spec = importlib.util.spec_from_file_location("pp", os.path.join(os.path.dirname(os.path.abspath(__file__)), "process_pages.py"))
pp = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(pp)

SRC = r"D:\Downloads\333"
OUT = r"D:\Downloads\333_out"


def expected(seq):
    return 2 * seq - 1 if seq <= 90 else 2 * (seq - 90)


def ocr_runs(img_gray_strip, psms=(6, 7), scales=(2, 3)):
    texts = []
    for sc in scales:
        im = img_gray_strip.resize((img_gray_strip.width * sc, img_gray_strip.height * sc), Image.LANCZOS)
        for psm in psms:
            t = pytesseract.image_to_string(
                im, config=f"--psm {psm} -c tessedit_char_whitelist=0123456789").strip()
            texts.append(t)
    runs = []
    for t in texts:
        runs += re.findall(r"\d{1,3}", t)
    return [int(r) for r in runs], texts


def read_page_number(cleaned_bgr, exp):
    """在矫正后图上读页码,返回 (page, confirmed, detail)"""
    if cleaned_bgr.ndim == 2:
        gray = cleaned_bgr
    else:
        gray = cv2.cvtColor(cleaned_bgr, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    pil = Image.fromarray(gray)
    for hfrac in (0.10, 0.085, 0.13):
        strip = pil.crop((0, 0, W, int(H * hfrac)))
        strip = ImageOps.autocontrast(strip)
        runs, _ = ocr_runs(strip)
        if exp in runs:
            return exp, True, f"confirmed({exp})"
        # 找出范围内最可能的页码
        cand = [r for r in runs if 1 <= r <= 180]
        if cand:
            # 若候选里有与exp奇偶一致的,优先
            same_par = [c for c in cand if c % 2 == exp % 2]
            pick = same_par[0] if same_par else cand[0]
            if pick == exp:
                return exp, True, f"confirmed({exp})"
            # 记录疑似但不改判
            detail = f"OCR疑读{pick}(候选{cand})"
        else:
            detail = f"未读到(runs={runs})"
    return exp, False, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-width", type=int, default=2400)
    ap.add_argument("--color", action="store_true")
    ap.add_argument("--pdf", default="")
    ap.add_argument("--dry-run", action="store_true", help="只跑OCR验证,不写图片")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    files = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".jpg"))
    if args.limit:
        files = files[:args.limit]

    rows = []
    flagged = []
    for i, fn in enumerate(files, 1):
        src = os.path.join(SRC, fn)
        exp = expected(i)
        img = cv2.imread(src)
        quad = pp.find_page_quad(img)
        if quad is None:
            warped = img
        else:
            warped = pp.warp_page(img, quad, args.max_width)
        ph, pw = warped.shape[:2]
        dy, dx = int(ph * 0.005), int(pw * 0.005)
        warped = warped[dy:ph - dy, dx:pw - dx]

        if args.color:
            lab = cv2.cvtColor(warped, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab); l = pp.enhance(l)
            out = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
        else:
            out = pp.enhance(cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY))

        page, confirmed, detail = read_page_number(out, exp)
        row = {"seq": i, "src": fn, "page": page, "expected": exp,
               "confirmed": confirmed, "detail": detail}
        rows.append(row)
        if not confirmed:
            flagged.append(row)
        status = "OK " if confirmed else "!! "
        print(f"{status}[{i:3}] {fn} -> page_{page:03d}  exp={exp}  {detail}", flush=True)

        if not args.dry_run:
            dst = os.path.join(OUT, f"page_{page:03d}.jpg")
            cv2.imwrite(dst, out, [cv2.IMWRITE_JPEG_QUALITY, 92])

    with open(os.path.join(OUT, "mapping.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["seq", "src", "page", "expected", "confirmed", "detail"])
        w.writeheader(); w.writerows(rows)

    print(f"\n==== 完成 {len(rows)} 页,未确认 {len(flagged)} ====")
    for r in flagged:
        print(f"  可疑: seq{r['seq']} {r['src']} exp={r['expected']} -> {r['detail']}")

    if args.pdf and not args.dry_run:
        import fitz
        doc = fitz.open()
        for r in sorted(rows, key=lambda x: x["page"]):
            p = os.path.join(OUT, f"page_{r['page']:03d}.jpg")
            if not os.path.exists(p):
                continue
            pix = fitz.open(p)[0].get_pixmap()
            page = doc.new_page(width=pix.width, height=pix.height)
            page.insert_image(fitz.Rect(0, 0, pix.width, pix.height), pixmap=pix)
        doc.save(args.pdf); doc.close()
        print(f"PDF: {args.pdf}")


if __name__ == "__main__":
    main()
