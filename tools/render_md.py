#!/usr/bin/env python3
"""把块模型输出为「给 AI 读」的 Markdown。

原则：
- 图片一律写成相对本地 Markdown 的 ![](../images/x.webp)，多模态模型可直接打开；
- 表格保持 Markdown 表格；皮肤/表情这类条目写成小标题 + 列表，方便 RAG 切块；
- 不塞导航、目录、编辑入口等噪声。
"""
import re

from render_page import pretty_name

MD_IMG = re.compile(r"\.(png|jpe?g|gif|webp)$", re.I)


def _in(tokens, img=True):
    out = []
    for tk in tokens:
        k = tk[0]
        if k in ("t", "b"):
            out.append(tk[1])
        elif k == "a":
            out.append(f"{tk[1]}（p{tk[2]}.md）")
        elif k in ("img", "imginline") and img:
            if tk[2]:
                label = MD_IMG.sub("", tk[4] or pretty_name(tk[1]))
                out.append(f"![{label}]({tk[2]})")
    s = "".join(out)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def _in_plain(tokens):
    return _in(tokens, img=False)


def _table(b):
    head, rows = b.get("head") or [], b["rows"]
    imgs = b.get("imgs") or []
    w = max([len(head)] + [len(r) for r in rows]) if rows else 0
    if not w:
        return ""
    if not head:
        head = [[] for _ in range(w)]
    lines = ["| " + " | ".join(_in_plain(c).replace("|", "\\|") for c in head) + " |",
             "| " + " | ".join(["---"] * w) + " |"]
    for i, row in enumerate(rows):
        cells = []
        for j, c in enumerate(row + [[]] * (w - len(row))):
            v = _in_plain(c).replace("|", "\\|")
            if j == 0 and imgs and i < len(imgs) and imgs[i].get("path"):
                nm = imgs[i].get("name") or "图片"
                v = (v + " " if v else "") + f"![{MD_IMG.sub('', pretty_name(nm))}]({imgs[i]['path']})"
            cells.append(v)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def block_md(b):
    t = b["t"]
    if t == "p":
        body = _in(b["in"])
        return body
    if t == "pre":
        return "```\n" + b["text"] + "\n```"
    if t == "ul":
        out = []
        for it in b["items"]:
            out.append("  " * it.get("lv", 0) + "- " + _in(it["in"]))
        return "\n".join(out)
    if t == "dl":
        return "\n".join(f"- **{_in_plain(it['k'])}**：{_in(it['v'])}" for it in b["items"])
    if t == "table":
        return _table(b)
    if t == "gal":
        out = []
        for it in b["items"]:
            cap = it.get("cap") or pretty_name(it["name"])
            out.append(f"![{cap}]({it['path']})")
        return "\n\n".join(out) if len(out) <= 6 else " ".join(out)
    if t == "pass":
        tracks = ("免费", "付费", "付费+升级")
        lines = ["| 等级 | " + " | ".join(tracks) + " |",
                 "| --- | " + " | ".join(["---"] * len(tracks)) + " |"]
        for r in b["rows"]:
            cells = []
            for i in range(len(tracks)):
                a = r["awards"][i] if i < len(r["awards"]) else None
                if not a:
                    cells.append("—")
                    continue
                label = MD_IMG.sub("", pretty_name(a["name"])) if a.get("name") else ""
                bit = ""
                if a.get("path"):
                    bit += f"![{label}]({a['path']})"
                if a.get("num"):
                    bit += " " + a["num"]
                cells.append(bit.strip() or "—")
            lines.append(f'| {r["level"]} | ' + " | ".join(cells) + " |")
        return "\n".join(lines)
    if t == "fig":
        cap = b.get("cap") or pretty_name(b["name"])
        return f"![{cap}]({b['path']})"
    return ""


def doc_md(doc, opts):
    title = opts.get("title", "")
    cat = opts.get("category", "")
    meta = [f"> 分类：{cat}"]
    for k, v in opts.get("chips") or []:
        meta.append(f"> {k}：{v}")
    if opts.get("source"):
        meta.append(f"> 来源：{opts['source']}")
    out = [f"# {title}", " · ".join(x.lstrip("> ") for x in meta[0:1])]
    out = [f"# {title}", "\n".join(meta), ""]

    for s in doc.get("sections", []):
        if not s["blocks"] or s["title"] in ("目录", "视频"):
            continue
        lv = min(max(s["level"], 2), 5)
        if s["title"]:
            out.append("#" * lv + " " + s["title"])
            out.append("")
        for b in s["blocks"]:
            txt = block_md(b)
            if txt:
                out.append(txt)
                out.append("")
    return "\n".join(out).strip() + "\n"


# ---------------------------------------------------------------- 角色
def char_md(c, opts):
    out = [f"# {c['name']}" + (f"（{c['title']}）" if c["title"] else "")]
    meta = ["角色"]
    if c["number"]:
        meta.append(f"编号 {c['number']}")
    if c["period"]:
        meta.append(f"时期 {c['period']}")
    if c["gender"]:
        meta.append(c["gender"])
    out.append(f"> 分类：{' · '.join(meta)}")
    if opts.get("source"):
        out.append(f"> 来源：{opts['source']}")
    out.append("")

    if c["bio"]:
        out.append(c["bio"][0])
        out.append("")

    if c["stats"]:
        out.append("## 战斗数值")
        out.append("")
        out.append("| " + " | ".join(s["k"] for s in c["stats"]) + " |")
        out.append("| " + " | ".join("---" for _ in c["stats"]) + " |")
        out.append("| " + " | ".join(s["v"] for s in c["stats"]) + " |")
        out.append("")

    if c["skills"]:
        out.append("## 技能")
        out.append("")
        for s in c["skills"]:
            head = f"### {s['kind']}技能：{s['name']}"
            if s["cd"]:
                head += f"（冷却 {s['cd']}）"
            out.append(head)
            out.append("")
            out.append(s["desc"] or "—")
            out.append("")
            if s.get("pve"):
                out.append(f"**PVE**：{s['pve']}")
                out.append("")
        if c["potential"]:
            out.append(f"**潜能激发**：{c['potential']}")
            out.append("")
        if c["skill_note"]:
            out.append(f"**技能细节**：{c['skill_note']}")
            out.append("")

    kv = [("姓名", c["full_name"]), ("英文名", c["en"]), ("日文名", c["jp"]),
          ("从属组织", c["org"]), ("事件经历", c["event"]),
          ("上线时间", c["released"]), ("生日", c["birthday"]),
          ("喜欢食物", c["food"]), ("初始骰子", c["dice"]),
          ("礼物", "、".join(c["gifts"])), ("徽章", "、".join(c["badges"]))]
    kv = [(k, v) for k, v in kv if v]
    if kv:
        out.append("## 基础资料")
        out.append("")
        for k, v in kv:
            out.append(f"- {k}：{v}")
        out.append("")

    if c["pve"]:
        out.append("## PVE 特性")
        out.append("")
        for x in c["pve"]:
            out.append(f"- {x}")
        out.append("")

    # ---- 皮肤 ----
    out.append(f"## 皮肤（共 {len(c['skins'])} 套）")
    out.append("")
    out.append("> 皮肤编号取自素材文件名；「默认」「羁绊皮肤」也是独立皮肤。")
    out.append("")
    for i, sk in enumerate(c["skins"], 1):
        tag = []
        if sk.get("tier"):
            tag.append(f"{sk['tier']}品质")
        if sk["kind"] == "default":
            tag.append("初始")
        if sk["kind"] == "bond":
            tag.append("羁绊解锁")
        head = f"### {i}. {sk['name']}"
        if tag:
            head += "（" + " · ".join(tag) + "）"
        out.append(head)
        out.append("")
        if sk.get("acquire"):
            out.append(f"- 获取方式：{sk['acquire']}")
        if sk.get("code"):
            out.append(f"- 素材编号：{sk['code']}")
        # 图片
        for key in ("art", "art_sfw", "chibi", "head", "headq", "bust_low", "bust_high"):
            v = sk["imgs"].get(key)
            if v and v.get("path"):
                label = {"art": "立绘", "art_sfw": "立绘（和谐版）", "chibi": "Q版立绘",
                         "head": "头像", "headq": "Q版头像",
                         "bust_low": "半身像（星币<20）",
                         "bust_high": "半身像（星币≥20）"}[key]
                out.append(f"- {label}：![{sk['name']}{label}]({v['path']})")
        if sk.get("story"):
            out.append("")
            out.append(f"**皮肤故事**：{sk['story']}")
        out.append("")

    # ---- 表情 ----
    if c["emojis"]:
        out.append(f"## 表情（共 {len(c['emojis'])} 个）")
        out.append("")
        out.append("| # | 名称 | 品质 | 获取方式 | 图片 |")
        out.append("| --- | --- | --- | --- | --- |")
        for i, em in enumerate(c["emojis"], 1):
            out.append(f"| {i} | {em['name']} | {em.get('quality','')} | "
                       f"{em.get('acquire','')} | ![{em['name']}]({em['img']}) |")
        out.append("")

    # ---- 装扮 ----
    cos = c["cosmetics"]
    labels = {"头像": "头像", "名片": "名片", "卡牌": "卡牌", "骰子": "骰子", "主页背景": "主页背景"}
    got = [(k, cos.get(k) or []) for k in labels]
    got = [(k, v) for k, v in got if v]
    if got:
        out.append("## 装扮")
        out.append("")
        for k, rows in got:
            out.append(f"### {k}（{len(rows)}）")
            out.append("")
            out.append("| 名称 | 品质 | 获取方式 |")
            out.append("| --- | --- | --- |")
            for r in rows:
                out.append(f"| {r['name']} | {r.get('quality','')} | {r.get('acquire','')} |")
            out.append("")
    else:
        out.append("## 装扮")
        out.append("")
        out.append("官方 wiki 未提供该角色的 /获取 页，头像、名片、卡牌、骰子清单暂缺。")
        out.append("")

    if c["bio"][1:]:
        out.append("## 人物传记")
        out.append("")
        for p in c["bio"][1:]:
            out.append(p)
            out.append("")

    if c["others"]:
        out.append("## 画廊其他素材")
        out.append("")
        for o in c["others"]:
            out.append(f"- {o['cap']}：![{o['cap']}]({o['path']})")
        out.append("")

    if c["voices"]:
        out.append(f"## 语音台词（{len(c['voices'])} 条，中文）")
        out.append("")
        out.append("| 场景 | 台词 |")
        out.append("| --- | --- |")
        for v in c["voices"]:
            out.append(f"| {v['scene']} | {v['text']} |")
        out.append("")
    return "\n".join(out).strip() + "\n"


def render_md(doc, opts):
    if opts.get("char"):
        return char_md(opts["char"], opts)
    return doc_md(doc, opts)
