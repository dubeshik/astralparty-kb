#!/usr/bin/env python3
"""极简 DOM 解析与工具函数（无第三方依赖）。

只服务于知识库构建：把 wiki 输出的 HTML 变成可遍历的 Node 树。
"""
import html as _html
import re
from html.parser import HTMLParser

VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "col",
        "area", "base", "embed", "param", "track"}

# 完全丢弃的标签
DROP = {"script", "style", "noscript", "textarea", "svg", "canvas", "input",
        "button", "select", "form", "iframe", "video", "audio", "map", "object"}

# 视为块级容器的标签
BLOCK = {"div", "p", "center", "section", "table", "ul", "ol", "dl", "figure",
         "blockquote", "pre", "header", "footer", "aside", "nav", "article",
         "tbody", "tr", "td", "th", "li", "hr", "h1", "h2", "h3", "h4", "h5", "h6"}

INLINE_KEEP = {"b", "strong", "i", "em", "u", "s", "sub", "sup", "small",
               "code", "mark", "span", "a", "img", "br", "abbr", "kbd"}


class Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag, attrs=None):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.children = []          # 混合 Node / str

    def get(self, key, default=""):
        return self.attrs.get(key, default)

    def cls(self):
        return self.attrs.get("class", "")

    def __repr__(self):
        return f"<{self.tag} {self.attrs.get('class','')}>"


class DOM(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].children.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(text):
    d = DOM()
    try:
        d.feed(text or "")
    except Exception:
        pass
    return d.root


def text_of(n, skip_tags=None):
    if isinstance(n, str):
        return n
    if n.tag in (skip_tags or ()):
        return ""
    return "".join(text_of(c, skip_tags) for c in n.children)


def norm_space(s):
    s = re.sub(r"[\s\u00a0\u200b]+", " ", s or "")
    return s.strip()


def collapse(s):
    """压缩空白，但保留段落换行。"""
    s = (s or "").replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def esc(s):
    return _html.escape(str(s or ""), quote=True)


def walk(node, fn):
    """先序遍历，fn 返回 False 可剪枝。"""
    for c in list(node.children):
        if isinstance(c, str):
            continue
        if fn(c) is False:
            continue
        walk(c, fn)


def find_all(node, pred, out=None):
    out = [] if out is None else out
    for c in node.children:
        if isinstance(c, str):
            continue
        if pred(c):
            out.append(c)
        find_all(c, pred, out)
    return out


def find_first(node, pred):
    if isinstance(node, str):
        return None
    for c in node.children:
        if isinstance(c, str):
            continue
        if pred(c):
            return c
        got = find_first(c, pred)
        if got is not None:
            return got
    return None


def has_block_child(node):
    for c in node.children:
        if isinstance(c, str):
            continue
        if c.tag in BLOCK or is_gallery(c):
            return True
    return False


def is_gallery(n):
    """wiki 的图片墙：ul.gallery / div.custom-gallery / div.srf-gallery。"""
    cls = n.cls()
    if n.tag in ("ul", "div") and "gallery" in cls and "gallerytext" not in cls:
        return True
    return False


def gallery_boxes(n):
    """取画廊里的每个格子。"""
    boxes = find_all(n, lambda x: "gallerybox" in x.cls())
    if boxes:
        return boxes
    # 兜底：直接取直接子 li
    return [c for c in n.children if not isinstance(c, str) and c.tag == "li"]


def is_noise(n):
    """站务/导航/装饰类节点。"""
    if not isinstance(n, Node):
        return False
    tag = n.tag
    if tag in DROP:
        return True
    nid = n.get("id")
    cls = n.cls()
    if nid in ("bread-edit", "toc", "TB-OF", "mw-toc-heading", "RelicBase"):
        return True
    if cls and any(k in cls for k in ("mw-editsection", "noprint", "toc",
                                      "charabtn", "bread-edit", "mw-toc",
                                      "boxcc0", "custom-gallery-nav")):
        return True
    style = n.get("style", "").replace(" ", "")
    if "display:none" in style or "visibility:hidden" in style:
        return True
    if n.get("aria-hidden") == "true":
        return True
    return False
