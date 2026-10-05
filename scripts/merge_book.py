#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图书扫描奇偶页合并脚本
============================

适用场景:
  你已扫完奇数页(1,3,5...)和偶数页(2,4,6...),需要合并成正确的 1,2,3,4... 顺序 PDF。

两种命名模式:
  [模式A 推荐] 文件名含真实页码,如 p001.jpg / page_003.png / 005.tif
     -> 脚本按页码排序,奇偶交错,无需处理反转。
  [模式B] 文件名只是扫描顺序 001.jpg,002.jpg...
     -> 奇数页一组、偶数页一组(按扫描顺序命名)。
     -> 翻书扫偶数页会导致偶数页序列反向,需加 --flip-even 反转。

用法:
  # 预览合并序列(不生成PDF,先核对)
  python merge_book.py --input-dir "D:/scan" --dry-run

  # 模式A:按文件名页码合并
  python merge_book.py --input-dir "D:/scan" --output "D:/book.pdf"

  # 模式B:顺序命名 + 偶数页反向 + 偶数页旋转180°
  python merge_book.py --input-dir "D:/scan" --output "D:/book.pdf" \
        --flip-even --rotate-even 180

  # 合并后做OCR(需已安装 pymupdf,可选 tesseract 做文字层)
  python merge_book.py --input-dir "D:/scan" --output "D:/book.pdf" --ocr

依赖:
  pip install pymupdf
  (OCR 文字层可选,需另行安装 tesseract + 对应语言包)
"""

import argparse
import glob
import os
import re
import sys

IMG_EXTS = ("*.jpg", "*.jpeg", "*.png", "*.tif", "*.tiff", "*.bmp", "*.gif")

PAGE_NUM_RE = re.compile(r"(\d+)")


def collect_images(input_dir):
    files = []
    for ext in IMG_EXTS:
        files.extend(glob.glob(os.path.join(input_dir, ext)))
        files.extend(glob.glob(os.path.join(input_dir, ext.upper())))
    # 去重并排序(默认按文件名)
    files = sorted(set(files), key=lambda p: os.path.basename(p).lower())
    return files


def parse_page_number(path):
    """从文件名提取第一个数字串作为页码。失败返回 None。"""
    m = PAGE_NUM_RE.search(os.path.basename(path))
    return int(m.group(1)) if m else None


def build_sequence(files, flip_even, mode_a):
    """
    返回 (ordered_list, report)
    ordered_list: 最终页面顺序的文件路径列表
    """
    report = []

    if mode_a:
        # 模式A:用文件名中的页码
        numbered = []
        for f in files:
            pn = parse_page_number(f)
            if pn is None:
                report.append(f"  [警告] 无法从 '{os.path.basename(f)}' 解析页码,已跳过")
                continue
            numbered.append((pn, f))
        numbered.sort(key=lambda x: x[0])
        # 按页码顺序排列即正确(奇偶已自然交错)
        ordered = [f for _, f in numbered]
        report.append(f"模式A:按文件名页码排序,共 {len(ordered)} 页")
        return ordered, report

    # 模式B:按扫描顺序,前一半奇数后一半偶数(假设两组数量相等)
    n = len(files)
    half = n // 2
    odds = files[:half]          # 1,3,5... 扫描顺序
    evens = files[half:]         # 2,4,6... 扫描顺序(可能反向)
    if flip_even:
        evens = list(reversed(evens))
        report.append("模式B:已对偶数页序列执行反转(--flip-even)")
    else:
        report.append("模式B:未反转偶数页(若翻书扫描请加 --flip-even)")
    # 交错
    ordered = []
    for o, e in zip(odds, evens):
        ordered.append(o)
        ordered.append(e)
    # 若两组数量不等,补上多出来的
    if len(odds) > len(evens):
        ordered.extend(odds[len(evens):])
    elif len(evens) > len(odds):
        ordered.extend(evens[len(odds):])
    report.append(f"模式B:奇数 {len(odds)} 页, 偶数 {len(evens)} 页, 合并 {len(ordered)} 页")
    return ordered, report


def rotate_if_needed(page, rotate_even, is_even):
    if rotate_even and is_even and rotate_even != 0:
        page.set_rotation(rotate_even)


def make_pdf(ordered, output, rotate_even, dpi):
    import fitz  # pymupdf

    doc = fitz.open()
    for idx, f in enumerate(ordered):
        is_even = (idx % 2 == 1)  # 合并后第2,4,6...位为原偶数页
        img = fitz.open(f)
        # 用 pixmap 控制 dpi
        pix = img[0].get_pixmap(dpi=dpi)
        rect = fitz.Rect(0, 0, pix.width, pix.height)
        p = doc.new_page(width=rect.width, height=rect.height)
        p.insert_image(rect, pixmap=pix)
        if rotate_even and is_even and rotate_even != 0:
            p.set_rotation(rotate_even)
        img.close()
    doc.save(output)
    doc.close()


def main():
    ap = argparse.ArgumentParser(description="图书扫描奇偶页合并")
    ap.add_argument("--input-dir", required=True, help="扫描图片所在目录")
    ap.add_argument("--output", default="merged_book.pdf", help="输出 PDF 路径")
    ap.add_argument("--flip-even", action="store_true", help="模式B:反转偶数页序列(翻书扫描时用)")
    ap.add_argument("--rotate-even", type=int, default=0, choices=[0, 90, 180, 270],
                    help="对合并后的偶数页旋转角度(修正翻书导致的180°颠倒)")
    ap.add_argument("--dpi", type=int, default=200, help="输出 PDF 渲染 DPI")
    ap.add_argument("--mode-a", dest="mode_a", action="store_true",
                    help="按文件名中的页码排序(默认:自动检测,有页码则模式A)")
    ap.add_argument("--mode-b", dest="mode_a", action="store_false",
                    help="强制模式B(扫描顺序命名)")
    ap.add_argument("--dry-run", action="store_true", help="只打印合并序列,不生成 PDF")
    ap.set_defaults(mode_a=None)
    args = ap.parse_args()

    if not os.path.isdir(args.input_dir):
        print(f"[错误] 目录不存在: {args.input_dir}")
        sys.exit(1)

    files = collect_images(args.input_dir)
    if not files:
        print(f"[错误] 目录中未找到图片: {args.input_dir}")
        sys.exit(1)

    # 自动检测模式:只要存在可解析页码的文件即视为模式A
    if args.mode_a is None:
        has_num = any(parse_page_number(f) is not None for f in files)
        mode_a = has_num
    else:
        mode_a = args.mode_a

    ordered, report = build_sequence(files, args.flip_even, mode_a)
    for line in report:
        print(line)

    print("\n合并序列预览(前20 / 后20):")
    head = ordered[:20]
    tail = ordered[-20:] if len(ordered) > 20 else []
    for i, f in enumerate(head):
        print(f"  {i+1:>4}: {os.path.basename(f)}")
    if tail and tail != head:
        print("   ...")
        for i, f in enumerate(tail):
            print(f"  {len(ordered)-len(tail)+i+1:>4}: {os.path.basename(f)}")

    if args.dry_run:
        print("\n[dry-run] 未生成 PDF。确认序列正确后去掉 --dry-run 重新运行。")
        return

    try:
        make_pdf(ordered, args.output, args.rotate_even, args.dpi)
        print(f"\n[完成] 已生成: {args.output}  ({len(ordered)} 页)")
    except ImportError:
        print("[错误] 缺少 pymupdf,请运行: pip install pymupdf")
        sys.exit(1)


if __name__ == "__main__":
    main()
