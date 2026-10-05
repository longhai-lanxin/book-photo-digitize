#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描页处理:去黑边 + 透视矫正 + 光照均匀化/增强
================================================
针对:深色垫板拍照 → 页面四周有黑边、拍摄有透视倾斜、光照不均。

流程:
  1. 灰度 + Otsu 二值化,分离亮色页面与深色垫板
  2. 取最大轮廓 → 近似四边形(页面四角)
  3. 透视变换拉正为矩形(同时完成矫正)
  4. 光照均匀化(背景估计相除)+ CLAHE + 锐化

用法:
  # 预览单张
  python process_pages.py --input-dir "D:/Downloads/333_sorted" --output-dir "D:/Downloads/333_fixed" --limit 3
  # 全量
  python process_pages.py --input-dir "..." --output-dir "..." 
"""
import argparse, os, sys, glob
import cv2
import numpy as np


def order_quad(pts):
    """四点排序: 左上,右上,右下,左下"""
    pts = np.array(pts, dtype="float32").reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return np.array([tl, tr, br, bl], dtype="float32")


def find_page_quad(img):
    """返回页面四角(None 表示未找到)。"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    # Otsu:页面亮 -> 前景
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # 形态学闭运算,补齐页面内深色文字造成的空洞
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=3)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel, iterations=1)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    area = cv2.contourArea(c)
    h, w = gray.shape
    if area < 0.15 * h * w:      # 面积太小,判定失败
        return None
    peri = cv2.arcLength(c, True)
    approx = cv2.approxPolyDP(c, 0.02 * peri, True)
    if len(approx) == 4:
        return order_quad(approx.reshape(4, 2))
    # 退化:用最小外接矩形
    rect = cv2.minAreaRect(c)
    box = cv2.boxPoints(rect)
    return order_quad(box)


def warp_page(img, quad, max_w=2400):
    tl, tr, br, bl = quad
    wA = np.linalg.norm(br - bl)
    wB = np.linalg.norm(tr - tl)
    hA = np.linalg.norm(tr - br)
    hB = np.linalg.norm(tl - bl)
    w = int(max(wA, wB)); h = int(max(hA, hB))
    # 输出尺寸(限制最大宽度)
    if w > max_w:
        h = int(h * max_w / w); w = max_w
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(quad, dst)
    return cv2.warpPerspective(img, M, (w, h), flags=cv2.INTER_CUBIC)


def enhance(gray):
    # 光照均匀化:大核模糊估计背景,相除
    bg = cv2.GaussianBlur(gray, (0, 0), 55)
    norm = cv2.divide(gray, bg, scale=255)
    norm = np.clip(norm, 0, 255).astype(np.uint8)
    # 局部对比度
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    out = clahe.apply(norm)
    # 轻微锐化(USM)
    blur = cv2.GaussianBlur(out, (0, 0), 2)
    out = cv2.addWeighted(out, 1.4, blur, -0.4, 0)
    return out


def process_one(path, out_path, max_w, keep_color, crop_pad=0.004):
    img = cv2.imread(path)
    if img is None:
        return False, "读取失败"
    quad = find_page_quad(img)
    if quad is None:
        warped = img
        note = "未检出页面,未矫正"
    else:
        # 向内收一点,切掉残余黑边
        warped = warp_page(img, quad, max_w)
        note = "ok"
    if crop_pad > 0:
        ph, pw = warped.shape[:2]
        dy, dx = int(ph * crop_pad), int(pw * crop_pad)
        warped = warped[dy:ph - dy, dx:pw - dx]
    if keep_color:
        lab = cv2.cvtColor(warped, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = enhance(l)
        out = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    else:
        out = enhance(cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY))
    cv2.imwrite(out_path, out, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return True, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-width", type=int, default=2400)
    ap.add_argument("--color", action="store_true", help="保留彩色(默认灰度高对比,适合文字)")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 张(预览用)")
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(args.input_dir, "*.jpg")) +
                   glob.glob(os.path.join(args.input_dir, "*.png")))
    if args.limit:
        files = files[:args.limit]
    ok = fail = 0
    for f in files:
        out = os.path.join(args.output_dir, os.path.basename(f))
        good, note = process_one(f, out, args.max_width, args.color)
        print(f"{'OK ' if good else 'ERR'} {os.path.basename(f)}  {note}", flush=True)
        ok += good; fail += (not good)
    print(f"\n完成: 成功 {ok}, 失败 {fail}")


if __name__ == "__main__":
    main()
