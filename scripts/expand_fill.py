#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
expand_fill.py
把 PDF 每页实际显示的那张图，无损地拉伸/铺满到"当前页面尺寸"（去除四周留白）。

- 只取页面"实际显示"的图（get_image_info），丢弃未绘制的冗余资源。
- 原样搬移图片字节流（PNG/JPEG 原流），不重新编码 → 无损。
- 保留软掩码（smask）作为 alpha。
- keep_proportion=False → 图片被拉伸到与页面矩形完全一致（填满整页）。

用法:
  python expand_fill.py --input in.pdf --output out.pdf [--limit N]
"""
import argparse, os, sys
import fitz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 页（0=全部），用于试跑")
    args = ap.parse_args()

    src = fitz.open(args.input)
    out = fitz.open()
    n = src.page_count if args.limit <= 0 else min(args.limit, src.page_count)

    for i in range(n):
        pg = src[i]
        infos = pg.get_image_info(xrefs=True)
        if not infos:
            # 无显示图的页面：原样复制该页（保持不丢页）
            out.insert_pdf(src, from_page=i, to_page=i)
            print(f"[{i+1:3}] 无显示图 → 原样复制")
            continue

        # 取面积最大的显示图作为正文
        info = max(infos, key=lambda z: z["width"] * z["height"])
        xref = info["xref"]
        d = src.extract_image(xref)
        img_bytes = d["image"]
        mask_bytes = None
        if d.get("smask"):
            md = src.extract_image(d["smask"])
            mask_bytes = md["image"]

        r = pg.rect  # 当前页面尺寸（A4）
        np_ = out.new_page(width=r.width, height=r.height)
        np_.insert_image(
            np_.rect,
            stream=img_bytes,
            mask=mask_bytes,
            keep_proportion=False,   # 拉伸铺满整页
        )
        if i % 20 == 0 or i == n - 1:
            print(f"[{i+1:3}] {r.width:.1f}x{r.height:.1f} <- 图 {d['width']}x{d['height']} {d['ext']}"
                  f"{' +mask' if mask_bytes else ''}")

    out.save(args.output, deflate=True, garbage=4)
    print(f"\n完成: {out.page_count} 页 -> {args.output}")
    print("大小: %.1f MB" % (os.path.getsize(args.output) / 1024 / 1024))
    out.close()
    src.close()


if __name__ == "__main__":
    main()
