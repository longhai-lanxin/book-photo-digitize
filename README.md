# book-photo-digitize

把手机拍摄的图书/试卷照片批量电子化——透视矫正、去黑边、四周黑边/灰带/贴边杂噪补白（含逐页校验）、增强，逐页 OCR 读取页眉页码，按真实页码排序重命名并合成 PDF，可选把正文图拉伸铺满整页。适用于深色垫板拍照（有黑边）、有透视倾斜、奇偶页页码分居左右上角的扫描件。触发词：图书电子化、扫描件矫正、去黑边、黑边补白、边缘竖向暗条、灰带补白、页码排序重命名、奇偶页合并、扫描书转PDF。

## Install

```bash
git clone https://github.com/longhai-lanxin/book-photo-digitize.git ~/.workbuddy/skills/book-photo-digitize
```

Compatible with any agent that reads `SKILL.md` frontmatter (WorkBuddy / CodeBuddy / Claude-style skills).

## Layout

```
|- scripts/
|  |- build_book.py
|  |- expand_fill.py
|  |- merge_book.py
|  |- ocr_pagenum.py
|  |- process_pages.py
|  |- verify_border.py
|  `- whiten_border.py
|- README.md
`- SKILL.md
```

## License

MIT
