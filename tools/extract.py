#!/usr/bin/env python3
"""把 wiki 页面 HTML 解析成结构化「块模型」。

不经过 Markdown 往返，避免正文被拍平成一长条文字。
产物结构（每个页面）::

    {
      "title": "芬妮/画廊",
      "sections": [
        {"level": 2, "title": "图片", "blocks": [...]},
        {"level": 3, "title": "皮肤", "blocks": [...]},
        ...
      ],
      "props": [("中文名", "芬妮"), ...],      # 来自 wikitext 模板
      "tpl": "星趴角色画廊",
    }

块类型：
  p     段落      {"t":"p","in":[token...]}
  ul    列表      {"t":"ul","items":[{"in":[...],"lv":0}]}
  dl    键值      {"t":"dl","items":[{"k":[...],"v":[...]}]}
  table 表格      {"t":"table","head":[[tok]],"rows":[[[tok]]],"quality":[...]}
  gal   图片墙    {"t":"gal","items":[{"name","path","cap","kind"}]}
  fig   单图      {"t":"fig","name","path","cap","kind"}
token：("t",text) ("a",text,page_id) ("img",name,path,kind,alt) ("b",text)
"""
import re

import img_types
from domutil import (BLOCK, Node, collapse, esc, find_all, find_first,
                     has_block_child, is_gallery, is_noise, norm_space, parse,
                     text_of)

NOISE_TEXT = (
    "如果是第一次来", "请推荐给朋友", "按右上角", "返回顶部", "返回底部",
    "觉得WIKI好玩", "Ctrl+D", "点击展开/收起", "本页面正在施工",
    "协助编辑，感谢", "正在加载视频", "首次访问", "收藏随时查看更新",
)
SHORT_NAV = {"编", "刷", "历", "编辑", "返回顶部", "返回底部", "目录", "×", "x"}
# 底部导航模板 / 筛选器 / 卡片渲染器：不是正文
NAV_CLASSES = ("characterbox", "cardselectoption", "boxcc0", "boxcc",
               "cardselecttr", "divcardsort", "filtertable")
NAV_TEXTS = {"星趴筹码", "星趴角色", "星趴怪物", "星趴卡牌", "星趴角色图鉴",
             "星趴卡牌图鉴", "星趴地图图鉴", "星趴怪物图鉴", "星趴装扮",
             "星趴手牌", "星趴事件", "星趴地图", "星趴活动", "星趴道具",
             "展开/折叠", "全部展开", "全部折叠"}
# 视觉卡片渲染器：里面的图是拼出来的卡面，正文只留主图
CARD_VISUAL = ("hand-card", "relicpart", "cardmpb", "custombg")

# 皮肤分组这些标题是人工标签，不是正文
CATALOG_HEADS = {"头像", "q版头像", "立绘", "q版立绘", "当星币数＜20时",
                 "当星币数≥20时", "当星币数<20时", "当星币数>=20时",
                 "立绘（和谐版）", "起始点", "像素头像", "头像鼠"}


def clean_text(s):
    s = (s or "").replace("\u00a0", " ")
    s = re.sub(r"展开/折叠", "", s)
    s = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def heading_text(node):
    """标题文本：跳过 [编辑] 之类的编辑入口。"""
    parts = []

    def rec(n):
        if isinstance(n, str):
            parts.append(n)
            return
        if n.tag in ("script", "style"):
            return
        if "mw-editsection" in n.cls():
            return
        for c in n.children:
            rec(c)

    rec(node)
    t = clean_text("".join(parts))
    t = re.sub(r"\[\s*编辑\s*\]", "", t)
    return t.strip()


def _classify(name, cap):
    return img_types.classify(name, cap)


class Extractor:
    def __init__(self, img, title_to_id, page_id=None):
        self.img = img
        self.t2i = title_to_id
        self.page_id = page_id
        self.sections = []
        self.seen = set()          # 已出现过的逻辑图片名
        self.all_imgs = []         # 全页图片（用于挑选封面）
        self._no_img = False       # 卡面文字遍历期间不重复出图
        self._push("", 0)

    # ---------- 结构 ----------
    def _push(self, title, level):
        self.sections.append({"level": level, "title": title, "blocks": []})

    def _blocks(self):
        return self.sections[-1]["blocks"]

    def _emit(self, block):
        self._blocks().append(block)

    # ---------- 主流程 ----------
    def run(self, html):
        root = parse(html)
        self.walk(root)
        return self.result()

    def walk(self, node):
        buf = []           # 待冲刷的行内 token

        def flush():
            toks = _trim(buf)
            if toks:
                self._emit({"t": "p", "in": toks})
            buf.clear()

        for c in node.children:
            if isinstance(c, str):
                buf.append(("t", c))
                continue
            if is_noise(c):
                continue
            tag = c.tag
            if re.fullmatch(r"h[1-6]", tag):
                t = heading_text(c)
                if not t or t in SHORT_NAV:
                    continue
                flush()
                lv = int(tag[1])
                if lv <= 2:
                    self._push(t, 2)
                else:
                    self._push(t, lv)
                continue
            if tag == "hr":
                continue
            cls_low = c.cls().lower()
            if any(k in cls_low for k in NAV_CLASSES):
                continue
            if any(k in cls_low for k in CARD_VISUAL) and not self._no_img:
                flush()
                self.card_visual(c)
                continue
            if "clearpass" in cls_low or "show_award" in cls_low:
                flush()
                self.pass_rewards(c)
                continue
            if "panel" in cls_low.split() and "panel-group" not in cls_low:
                flush()
                self.panel(c)
                continue
            if is_gallery(c):
                if self._no_img:
                    continue
                flush()
                self.gallery(c)
                continue
            if tag == "table":
                flush()
                self.table(c)
                continue
            if tag in ("ul", "ol", "dl"):
                flush()
                self.listing(c)
                continue
            if tag == "p":
                inner = self.inline(c.children, cap="")
                toks = _trim([inner]) if isinstance(inner, list) else []
                if toks:
                    self._emit({"t": "p", "in": toks})
                continue
            if tag == "pre":
                t = text_of(c)
                if t.strip():
                    self._emit({"t": "pre", "text": t.rstrip()})
                continue
            if tag == "img":
                flush()
                self.figure(c, "")
                continue
            if tag in ("div", "center", "section", "blockquote", "figure",
                       "article", "header", "footer", "aside", "nav", "tbody"):
                if _is_breadcrumb(c):
                    continue
                if has_block_child(c):
                    flush()
                    self.walk(c)
                else:
                    inner = self.inline(c.children, cap="")
                    if inner:
                        buf.extend(inner)
                continue
            if tag == "a":
                inner = self.inline([c], cap="")
                if inner:
                    buf.extend(inner)
                continue
            # 其余行内
            inner = self.inline([c], cap="")
            if inner:
                buf.extend(inner)
        flush()

    # ---------- 行内 ----------
    def inline(self, children, cap=""):
        out = []

        def add(x):
            if not x:
                return
            if isinstance(x, list):
                out.extend(x)
            else:
                out.append(x)

        for c in children:
            if isinstance(c, str):
                out.append(("t", c))
                continue
            if c.tag in ("script", "style", "noscript", "input", "button",
                         "select", "form", "iframe", "video", "audio", "svg"):
                continue
            if c.tag == "br":
                out.append(("t", " "))
                continue
            if c.tag == "img":
                if self._no_img:
                    continue
                name = self.img.name_of(c.get("src"))
                if not name:
                    continue
                path = self.img.local(name)
                alt = clean_text(c.get("alt"))
                kind = _classify(name, alt or cap)
                if kind != img_types.ICON:
                    self.all_imgs.append(name)
                try:
                    w = int(re.sub(r"[^\d]", "", c.get("width") or "0") or 0)
                except ValueError:
                    w = 0
                if kind == img_types.ICON or (w and w <= 64):
                    out.append(("img", name, path, kind, alt))
                else:
                    # 正文里的大图：单独成块，避免挤在句子里
                    out.append(("imginline", name, path, kind, alt))
                continue
            if c.tag == "a":
                href = c.get("href")
                txt = clean_text(text_of(c))
                pid = self._link_pid(c, href, txt)
                # 链接里包着图片
                imgs = find_all(c, lambda x: x.tag == "img")
                if pid and txt:
                    out.append(("a", txt, pid))
                    continue
                if imgs and not txt:
                    add(self.inline(c.children, cap))
                    continue
                if pid and not txt:
                    add(self.inline(c.children, cap))
                    continue
                if txt:
                    out.append(("t", txt))
                continue
            if c.tag in ("b", "strong"):
                t = clean_text(text_of(c))
                if t:
                    out.append(("b", t))
                continue
            add(self.inline(c.children, cap))
        return out

    def _link_pid(self, node, href, txt):
        cand = []
        if href:
            raw = href.split("#")[0].split("?")[0]
            if raw.startswith("/starengine/"):
                raw = raw[len("/starengine/"):]
            elif raw.startswith("./"):
                raw = raw[2:]
            if raw and not raw.startswith(("http", "javascript", "//")):
                import urllib.parse as up
                cand.append(up.unquote(raw))
        t = node.get("title")
        if t:
            cand.append(t)
        if txt:
            cand.append(txt)
        for c in cand:
            c = c.replace("_", " ")
            pid = self.t2i.get(c)
            if pid:
                return None if pid == self.page_id else pid
        return None

    # ---------- 图片 ----------
    def panel(self, node):
        """Bootstrap 折叠面板：标题作为小节，正文继续走 walk。"""
        title = ""
        for t in find_all(node, lambda x: "panel-title" in x.cls()):
            title = clean_text(text_of(t))
            if title:
                break
        if title:
            title = re.sub(r"展开/折叠", "", title).strip()
            if title and title != self.sections[-1]["title"]:
                self._push(title, 4)
        for c in node.children:
            if isinstance(c, str):
                continue
            if "panel-heading" in c.cls():
                continue
            self.walk_into(c)

    def walk_into(self, node):
        """只遍历 node 的子节点（不重复处理 node 自身）。"""
        for c in list(node.children):
            holder = Node("holder")
            holder.children = [c]
            self.walk(holder)

    def pass_rewards(self, node):
        """通行证奖励墙：每一级若干奖励，渲染成「等级 -> 奖励」表。"""
        rows = []
        for la in find_all(node, lambda x: "level_award" in x.cls()):
            lv = ""
            lvd = find_first(la, lambda x: x.cls().strip() == "level")
            if lvd is not None:
                lv = clean_text(text_of(lvd))
            awards = []
            for a in find_all(la, lambda x: x.cls().strip() == "award"):
                img_name, quality = "", ""
                for im in find_all(a, lambda x: x.tag == "img"):
                    name = self.img.name_of(im.get("src"))
                    if not name:
                        continue
                    low = name.lower()
                    if "稀有度" in name:
                        quality = _quality_from_name(name)
                        continue
                    if "actnum" in low:      # 数字黑底，不是奖励内容
                        continue
                    img_name = img_name or name
                num = ""
                nd = find_first(a, lambda x: x.cls().strip() == "rewardnum")
                if nd is not None:
                    num = clean_text(text_of(nd))
                if not num:
                    m = re.search(r"×\s*\d+", clean_text(text_of(a)))
                    num = m.group(0) if m else ""
                if img_name or num:
                    if img_name:
                        self.all_imgs.append(img_name)
                    awards.append({"name": img_name,
                                   "path": self.img.local(img_name) if img_name else "",
                                   "num": num, "quality": quality})
            if lv or awards:
                rows.append({"level": lv or "?", "awards": awards})
        if rows:
            self._emit({"t": "pass", "rows": rows})

    def card_visual(self, node):
        """卡面/筹码渲染器：保留主图与卡面文字，丢掉拼图的框与图标。"""
        best = ""
        for im in find_all(node, lambda x: x.tag == "img"):
            name = self.img.name_of(im.get("src"))
            if not name:
                continue
            if img_types.classify(name) == img_types.ICON:
                continue
            best = name
            break
        if best and best not in self.seen:
            self.seen.add(best)
            self.all_imgs.append(best)
            self._emit({"t": "fig", "name": best, "path": self.img.local(best),
                        "cap": "", "kind": img_types.classify(best)})
        # 卡面里的文字是正文（效果描述），要保留；图片已单独出块，不再重复
        self._no_img = True
        try:
            self.walk_into(node)
        finally:
            self._no_img = False

    def _img_item(self, name, cap):
        path = self.img.local(name)
        kind = _classify(name, cap)
        return {"name": name, "path": path, "cap": clean_text(cap), "kind": kind}

    def gallery(self, node):
        items = []
        for box in self._boxes(node):
            imgs = find_all(box, lambda x: x.tag == "img")
            if not imgs:
                continue
            caption = ""
            gt = find_first(box, lambda x: "gallerytext" in x.cls())
            if gt is not None:
                caption = clean_text(text_of(gt))
            if not caption:
                caption = clean_text(box.get("data-caption"))
            for im in imgs:
                name = self.img.name_of(im.get("src"))
                if not name:
                    continue
                alt = clean_text(im.get("alt"))
                cap = caption or alt
                kind = _classify(name, cap)
                if kind == img_types.ICON:
                    continue
                if name in self.seen:
                    continue
                self.seen.add(name)
                self.all_imgs.append(name)
                items.append({"name": name, "path": self.img.local(name),
                              "cap": cap, "kind": kind})
        if items:
            self._emit({"t": "gal", "items": items})

    def _boxes(self, node):
        boxes = find_all(node, lambda x: "gallerybox" in x.cls())
        if boxes:
            return boxes
        out = []
        for c in node.children:
            if isinstance(c, str):
                continue
            if c.tag == "li":
                out.append(c)
            elif c.tag in ("div", "ul"):
                out.extend(self._boxes(c))
        return out

    def figure(self, node, cap):
        name = self.img.name_of(node.get("src"))
        if not name:
            return
        alt = clean_text(node.get("alt"))
        kind = _classify(name, alt or cap)
        if kind == img_types.ICON or name in self.seen:
            return
        self.seen.add(name)
        self.all_imgs.append(name)
        self._emit({"t": "fig", "name": name, "path": self.img.local(name),
                    "cap": cap or alt, "kind": kind})

    # ---------- 列表 ----------
    def listing(self, node):
        if node.tag == "dl":
            self._definition_list(node)
            return
        items = []
        self._list_items(node, 0, items)
        if items:
            self._emit({"t": "ul", "items": items})

    def _definition_list(self, node):
        """<dl> 既可能是键值表，也被 wiki 当作缩进用（没有 dt 的 dd）。"""
        kv = []

        def flush_kv():
            if kv:
                self._emit({"t": "dl", "items": kv[:]})
                kv.clear()

        k = None
        for c in node.children:
            if isinstance(c, str):
                continue
            if c.tag == "dt":
                flush_kv()
                k = _trim(self.inline(c.children))
                continue
            if c.tag != "dd":
                continue
            toks, subs = [], []
            for cc in c.children:
                if isinstance(cc, str):
                    toks.append(("t", cc))
                elif cc.tag in ("ul", "ol", "dl"):
                    subs.append(cc)
                else:
                    toks.extend(self.inline([cc]) or [])
            t = _trim(toks)
            if k is not None:
                kv.append({"k": k, "v": t})
                k = None
            elif t:
                flush_kv()
                self._emit({"t": "p", "in": t, "indent": True})
            for s in subs:
                flush_kv()
                if s.tag == "dl":
                    self._definition_list(s)
                else:
                    items = []
                    self._list_items(s, 0, items)
                    if items:
                        self._emit({"t": "ul", "items": items})
        flush_kv()

    def _list_items(self, node, lv, out):
        for c in node.children:
            if isinstance(c, str):
                continue
            if c.tag != "li":
                continue
            # 直接的文本/行内
            toks = []
            subs = []
            for cc in c.children:
                if isinstance(cc, str):
                    toks.append(("t", cc))
                elif cc.tag in ("ul", "ol", "dl"):
                    subs.append(cc)
                else:
                    toks.extend(self.inline([cc]) or [])
            t = _trim(toks)
            if t:
                out.append({"in": t, "lv": lv})
            for s in subs:
                if s.tag == "dl":
                    self.listing(s)
                else:
                    self._list_items(s, lv + 1, out)

    # ---------- 表格 ----------
    def table(self, node):
        rows, quality, head, imgs = [], [], [], []
        for tr in find_all(node, lambda x: x.tag == "tr"):
            cells = [c for c in tr.children
                     if not isinstance(c, str) and c.tag in ("td", "th")]
            if not cells:
                continue
            if all(c.tag == "th" for c in cells) and not rows:
                head = [_trim(self.inline(c.children)) for c in cells]
                continue
            row, qrow, picked, q = [], [], "", ""
            for idx, c in enumerate(cells):
                toks, cq = self._cell(c)
                row.append(toks)
                qrow.append(cq)
                if idx == 0:
                    picked, q = self._cell_item(c)
                    q = q or cq
            rows.append(row)
            quality.append(qrow)
            imgs.append({"name": picked,
                         "path": self.img.local(picked) if picked else "",
                         "quality": q})
        if not rows:
            return
        block = {"t": "table", "head": head, "rows": rows, "quality": quality}
        if any(i["path"] for i in imgs):
            block["imgs"] = imgs
        self._emit(block)

    def _cell(self, c):
        toks = _trim(self.inline(c.children))
        q = ""
        for im in find_all(c, lambda x: x.tag == "img"):
            name = self.img.name_of(im.get("src"))
            if name and "稀有度" in name:
                q = _quality_from_name(name)
                break
        return toks, q

    def _cell_item(self, c):
        """单元格里的「物品」图：跳过稀有度底图与图标。"""
        picked, q = "", ""
        for im in find_all(c, lambda x: x.tag == "img"):
            name = self.img.name_of(im.get("src"))
            if not name:
                continue
            if "稀有度" in name:
                if not q:
                    q = _quality_from_name(name)
                continue
            if img_types.classify(name) == img_types.ICON:
                continue
            if not picked:
                picked = name
        return picked, q

    # ---------- 结果 ----------
    def result(self):
        secs = []
        for s in self.sections:
            blocks = _post(s["blocks"])
            if not blocks and not s["title"]:
                continue
            s["blocks"] = blocks
            secs.append(s)
        return {"sections": secs, "images": self.all_imgs}


QUALITY_MAP = {"橙": "橙", "金": "橙", "紫": "紫", "蓝": "蓝", "绿": "绿",
               "红": "红"}


def _quality_from_name(name):
    m = re.search(r"稀有度[\s_]*([橙金紫蓝绿红])", name)
    if m:
        return QUALITY_MAP.get(m.group(1), m.group(1))
    m = re.search(r"(Amethyst|Sapphire|Emerald|Ruby|Topaz|Ultimate)", name, re.I)
    if m:
        return m.group(1)
    return ""


def _trim(tokens):
    """去首尾空白，合并相邻文本，丢弃空块。"""
    out = []
    for tk in tokens:
        if tk is None:
            continue
        if isinstance(tk, list):
            out.extend(_trim(tk))
            continue
        if tk[0] == "t":
            s = tk[1]
            if not out and not s.strip():
                continue
            out.append(("t", s))
        else:
            out.append(tk)
    # 合并相邻 t
    merged = []
    for tk in out:
        if merged and tk[0] == "t" and merged[-1][0] == "t":
            merged[-1] = ("t", merged[-1][1] + tk[1])
        else:
            merged.append(tk)
    # 清理
    res = []
    for tk in merged:
        if tk[0] == "t":
            s = re.sub(r"[ \t]+", " ", tk[1])
            if not s:
                continue
            res.append(("t", s))
        else:
            res.append(tk)
    while res and res[0][0] == "t" and not res[0][1].strip():
        res.pop(0)
    while res and res[-1][0] == "t" and not res[-1][1].strip():
        res.pop()
    if res and res[0][0] == "t":
        res[0] = ("t", res[0][1].lstrip())
    if res and res[-1][0] == "t":
        res[-1] = ("t", res[-1][1].rstrip())
    text = "".join(t[1] for t in res if t[0] in ("t", "b", "a"))
    if not text.strip() and not any(t[0] == "img" for t in res):
        return []
    return res


def _is_breadcrumb(n):
    t = text_of(n)
    if len(t) > 160:
        return False
    if any(k in t for k in NOISE_TEXT):
        return True
    if "首页" in t and (">" in t or "›" in t):
        return True
    return False


def _post(blocks):
    """块后处理：同一节的图片墙合并、去掉空段、去重。"""
    out = []
    for b in blocks:
        if b["t"] == "p":
            txt = "".join(x[1] for x in b["in"] if x[0] in ("t", "b", "a"))
            if not txt.strip() and not any(x[0].startswith("img") for x in b["in"]):
                continue
            key = clean_text(txt)
            if key in SHORT_NAV or key in NAV_TEXTS:
                continue
        if b["t"] == "p" and out and out[-1]["t"] == "p":
            # 连续段落合并成一条，减少碎行
            prev = out[-1]
            prev["in"] = _trim(prev["in"] + [("t", " ")] + b["in"])
            continue
        if b["t"] == "fig" and out and out[-1]["t"] == "gal":
            out[-1]["items"].append({"name": b["name"], "path": b["path"],
                                     "cap": b["cap"], "kind": b["kind"]})
            continue
        out.append(b)
    return out


def extract(html, img, title_to_id, page_id=None):
    return Extractor(img, title_to_id, page_id).run(html)
