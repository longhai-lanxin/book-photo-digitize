#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
whiten_border.py
把扫描残留的四周黑边 / 灰带 / 贴边杂噪「补成白色」（不裁剪）。

三种方法叠加：
  A. 纸张掩码法：灰度阈值 → 最大亮连通域（纸张）→ 填洞 → 掩码内缩 shrink 像素 → 掩码外置白。
     适合整块的深色垫板边框（含旋转 / 异形边）。
  B. 逐边噪声带法：对四边分别统计「暗像素占比」沿边向内的剖面，
     找到第一段持续干净的空白页边（连续 G 列 / 行 暗占比 < T_clean），把该边界以外整条置白。
     用于清除贴着页边、底色偏亮因而躲过 A 的竖向 / 横向【暗】噪声条。
  C. 贴边非白带法（新增）：按每列 / 行【平均灰度】从页边向内扫描，
     找到第一段连续 run 列都达到「纸白 − tol」的干净纸面，把其外侧（含贴边）整条置白。
     用于清除底色【浅灰】、含孤立字符碎片 / 页边阴影的贴边杂噪带——
     这类带既不暗（骗过 B）也亮于 A 的阈值（躲过 A）。
     若最外圈本身就是纯白纸（大多数页），边界为 0，不动任何像素（天然安全）。

用法:
  python whiten_border.py --input in.pdf --output out.pdf [--limit N]
         [--thr 140] [--shrink 8] [--dark 110] [--clean 1.0] [--run 20] [--cap 0.10]
         [--ltol 4] [--lrun 8] [--lcap 0.026]
"""
import argparse, os
import numpy as np
import cv2
import fitz


def paper_mask(gray, thr=140):
    """纸张亮区掩码 (uint8 0/1)：最大亮连通域 + 填洞。"""
    bright = (gray > thr).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(bright, 8)
    if num <= 1:
        return None
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    m = (labels == idx).astype(np.uint8)
    pad = cv2.copyMakeBorder(m, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    ff = pad.copy()
    ffmask = np.zeros((ff.shape[0] + 2, ff.shape[1] + 2), np.uint8)
    cv2.floodFill(ff, ffmask, (0, 0), 1)
    holes = (ff == 0).astype(np.uint8)
    return (pad | holes)[1:-1, 1:-1]


def edge_band(fracs, t_clean=1.0, run=20, cap_frac=0.10):
    """【方法B】fracs: 从页边向内每列(行)的暗像素占比(0-1)。返回需置白的像素宽度(0=不置白)。"""
    n = len(fracs)
    cap = int(n * cap_frac)
    cnt = 0
    for d in range(n):
        if fracs[d] < t_clean / 100.0:
            cnt += 1
            if cnt >= run:
                d0 = d - run + 1
                return d0 if d0 <= cap else 0
        else:
            cnt = 0
    return 0


def light_band(means, paper, tol=4.0, run=8, cap_frac=0.026):
    """【方法C】means: 从页边向内每列(行)的平均灰度。返回需置白的像素宽度(0=不置白)。
    找到第一段连续 run 列都 >= 纸白-tol 的干净纸面，返回其外侧宽度（受限 cap）。"""
    n = len(means)
    cap = int(n * cap_frac)
    T = paper - tol
    k = 0
    while k < n:
        if means[k] >= T:
            j = k
            while j < n and means[j] >= T:
                j += 1
            if j - k >= run:               # 找到连续干净纸面
                return k if k <= cap else 0
            k = j
        else:
            k += 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--thr", type=int, default=140, help="纸张亮区阈值(A)")
    ap.add_argument("--shrink", type=int, default=8, help="纸张掩码内缩像素(A)")
    ap.add_argument("--dark", type=int, default=110, help="判定暗像素的灰度上限(B)")
    ap.add_argument("--clean", type=float, default=1.0, help="判定干净页边的暗占比百分比上限(B)")
    ap.add_argument("--run", type=int, default=20, help="持续干净的行/列数阈值(B)")
    ap.add_argument("--cap", type=float, default=0.10, help="单边最多置白比例(B)")
    ap.add_argument("--ltol", type=float, default=4.0, help="纸白容差(C)")
    ap.add_argument("--lrun", type=int, default=8, help="连续干净纸面的列/行数阈值(C)")
    ap.add_argument("--lcap", type=float, default=0.026, help="单边最多置白比例(C)")
    ap.add_argument("--compress", type=int, default=6, help="PNG 压缩级别 0-9")
    args = ap.parse_args()

    src = fitz.open(args.input)
    out = fitz.open()
    n = src.page_count if args.limit <= 0 else min(args.limit, src.page_count)
    skipped = []
    c_pages = []   # 方法C 生效的页

    for i in range(n):
        pg = src[i]
        infos = pg.get_image_info(xrefs=True)
        r = pg.rect
        if not infos:
            out.insert_pdf(src, from_page=i, to_page=i)
            print(f"[{i+1:3}] 无显示图 → 原样复制")
            continue

        info = max(infos, key=lambda z: z["width"] * z["height"])
        pm = fitz.Pixmap(src, info["xref"])
        arr = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
        rgb = np.ascontiguousarray(arr[..., :3])
        H, W = rgb.shape[:2]
        gray = rgb.mean(axis=2)

        # --- A. 纸张掩码填白 ---
        m = paper_mask(gray, args.thr)
        if m is not None and m.mean() >= 0.35:
            if args.shrink > 0:
                k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                              (2 * args.shrink + 1, 2 * args.shrink + 1))
                m = cv2.erode(m, k)
            out_img = np.where(m[..., None] > 0, rgb, 255).astype(np.uint8)
        else:
            out_img = rgb.copy()
            if m is not None:
                skipped.append(i + 1)

        # --- B. 逐边噪声带（暗） ---
        dark = (gray < args.dark).astype(np.float32)
        bands = {
            "top":    edge_band(dark.mean(axis=1),           args.clean, args.run, args.cap),
            "bottom": edge_band(dark[::-1].mean(axis=1),     args.clean, args.run, args.cap),
            "left":   edge_band(dark.mean(axis=0),           args.clean, args.run, args.cap),
            "right":  edge_band(dark[:, ::-1].mean(axis=0),  args.clean, args.run, args.cap),
        }

        # --- C. 贴边非白带（浅灰 / 杂噪） ---
        paper = float(np.percentile(gray, 97))
        prof = {
            "top":    gray.mean(axis=1),
            "bottom": gray[::-1].mean(axis=1),
            "left":   gray.mean(axis=0),
            "right":  gray[:, ::-1].mean(axis=0),
        }
        lbands = {k: light_band(v, paper, args.ltol, args.lrun, args.lcap)
                  for k, v in prof.items()}

        # 合并 B/C，取较大者
        w = {k: max(bands[k], lbands[k]) for k in bands}

        if w["top"]:
            out_img[:w["top"], :] = 255
        if w["bottom"]:
            out_img[H - w["bottom"]:, :] = 255
        if w["left"]:
            out_img[:, :w["left"]] = 255
        if w["right"]:
            out_img[:, W - w["right"]:] = 255

        if max(lbands.values()) > 0:
            c_pages.append((i + 1, dict(lbands)))

        ok, buf = cv2.imencode(".png", cv2.cvtColor(out_img, cv2.COLOR_RGB2BGR),
                               [cv2.IMWRITE_PNG_COMPRESSION, args.compress])
        data = buf.tobytes()
        page = out.new_page(width=r.width, height=r.height)
        page.insert_image(page.rect, stream=data, keep_proportion=False)

        if i % 20 == 0 or i == n - 1 or max(w.values()) > 40:
            print(f"[{i+1:3}] 图 {pm.width}x{pm.height} | B 上{bands['top']} 下{bands['bottom']} "
                  f"左{bands['left']} 右{bands['right']} | C 上{lbands['top']} 下{lbands['bottom']} "
                  f"左{lbands['left']} 右{lbands['right']}")

    out.save(args.output, deflate=True, garbage=4)
    print(f"\n完成: {out.page_count} 页 -> {args.output}")
    print("大小: %.1f MB" % (os.path.getsize(args.output) / 1024 / 1024))
    if c_pages:
        print(f"方法C 生效 {len(c_pages)} 页 (页号: 边界):")
        for pgno, lb in c_pages:
            det = " ".join(f"{k}{v}" for k, v in lb.items() if v > 0)
            print(f"  第{pgno}页: {det}")
    if skipped:
        print("掩码占比过低(仍做噪声带处理)页:", skipped)
    out.close()
    src.close()


if __name__ == "__main__":
    main()
