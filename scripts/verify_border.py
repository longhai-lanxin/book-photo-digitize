#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verify_border.py —— 校验「四周黑边/灰带补白」是否达标（不改文件，只读）

对 PDF 每一页的实际显示图，统计四边「最外 BAND 像素」的平均灰度：
  平均灰度 > WHITE_PASS  → 视为已填白（≈纸白）
  平均灰度 ≤ WHITE_PASS  → 残留（可能还有灰带/黑边）
并可选对比一个「参考(未处理)PDF」，列出每边原值 → 现值。

判据经验值：BAND=15, WHITE_PASS=245。目标：残留 0 处。
注意：BAND 别取太大（如 25px），否则会把正文右缘算进来，造成「假残留」。

用法:
  python verify_border.py --pdf clean.pdf [--ref sorted.pdf] [--band 15] [--pass 245]
"""
import argparse
import numpy as np
import fitz


def outer_means(doc, pno, band):
    pg = doc[pno]
    infos = pg.get_image_info(xrefs=True)
    if not infos:
        return None
    info = max(infos, key=lambda z: z["width"] * z["height"])
    pm = fitz.Pixmap(doc, info["xref"])
    a = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, pm.n)
    g = np.ascontiguousarray(a[..., :3]).astype(np.float32).mean(axis=2)
    H, W = g.shape
    return {
        "上": g[:band, :].mean(),
        "下": g[H - band:, :].mean(),
        "左": g[:, :band].mean(),
        "右": g[:, W - band:].mean(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--ref", default="")
    ap.add_argument("--band", type=int, default=15)
    ap.add_argument("--pass", dest="wpass", type=float, default=245.0)
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    ref = fitz.open(args.ref) if args.ref else None
    n = doc.page_count
    resid = []
    for i in range(n):
        em = outer_means(doc, i, args.band)
        if em is None:
            continue
        for k, v in em.items():
            if v < args.wpass:
                rm = None
                if ref is not None and i < ref.page_count:
                    r = outer_means(ref, i, args.band)
                    rm = r[k] if r else None
                resid.append((i + 1, k, v, rm))

    print(f"文件: {args.pdf}")
    print(f"总页 {n}, 外圈 {args.band}px, 判定阈值 >{args.wpass:.0f}")
    if not resid:
        print(f"✅ 0 处残留：全部页四边外圈均已填白。")
    else:
        print(f"⚠ {len(resid)} 处残留：")
        for pgno, k, v, rv in resid:
            extra = f" (原 {rv:.0f})" if rv is not None else ""
            print(f"  第{pgno}页 {k}边 = {v:.1f}{extra}")
    doc.close()
    if ref is not None:
        ref.close()


if __name__ == "__main__":
    main()
