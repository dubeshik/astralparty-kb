#!/usr/bin/env python3
"""构建吉星派对本地知识库。

产物
  data/pages/p<id>.html      可直接浏览的宽屏词条页
  data/markdown/p<id>.md     给 AI 读的 Markdown（含本地图片引用）
  data/index.json            页面索引
  data/chunks.jsonl          RAG 分块（带章节路径）
  data/characters.json       角色 / 皮肤 / 表情 / 装扮结构化数据
  data/categories.json       分类与分组
  data/bundle.js             查看器离线数据

用法: python tools/build_kb.py
"""
import collections
import json
import os
import re
import time
import urllib.parse

import chargear
import extract as extract_mod
import img_index
import render_md
import render_page
import tpl_layout
from chargear import clean, tpl_fields

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
OUT_PAGES = os.path.join(DATA, "pages")
OUT_MD = os.path.join(DATA, "markdown")
SOURCE = "https://wiki.biligame.com/starengine/"

# 分类 -> 侧边栏分组
GROUPS = [
    ("角色", ["角色"]),
    ("对局内容", ["卡牌/手牌", "筹码", "事件", "怪物", "地图"]),
    ("外观与通行证", ["装扮图鉴", "通行证"]),
    ("活动与版本", ["活动", "版本与公告"]),
    ("资料", ["图鉴", "成就", "剧情", "其他"]),
]

SUB_PAGES = ("/画廊", "/获取", "/筹码搭配", "/语音", "/剧情")


def norm_title(t):
    return re.sub(r"[_\s]+", " ", (t or "").strip())


def classify(rec, tpl, fields):
    title = rec["title"]
    cats = " ".join(rec.get("categories") or [])
    w = rec.get("wikitext") or ""
    if tpl.startswith("星趴角色") and "画廊" not in tpl:
        return "角色", "char"
    if "星趴筹码" in tpl:
        return "筹码", "relic"
    if "星趴怪物" in tpl:
        return "怪物", "monster"
    if "星趴手牌" in tpl or "星趴卡牌" in tpl:
        return "卡牌/手牌", "card"
    if "MapEvent" in tpl or "地图事件" in tpl:
        return "事件", "event"
    if "通行证" in title or "通行证" in cats:
        return "通行证", "pass"
    if "装扮" in title or "星趴装扮" in tpl:
        return "装扮图鉴", "cosmetic"
    if ("公告" in title or "版本更新" in title or "官方公告" in cats
            or "公告" in cats):
        return "版本与公告", "notice"
    if "图鉴" in title:
        return "图鉴", "index"
    if "成就" in title or "成就" in cats:
        return "成就", "achievement"
    if title.endswith("/剧情"):
        return "剧情", "story"
    if "地图" in cats or "地图事件" in cats:
        return "地图", "map"
    if "活动" in cats or "活动" in title:
        return "活动", "activity"
    if "图鉴" in cats:
        return "图鉴", "index"
    if "怪物" in cats:
        return "怪物", "monster"
    if "角色" in cats:
        return "角色", "char"
    if "手牌" in cats or "卡牌" in cats:
        return "卡牌/手牌", "card"
    if "筹码" in cats:
        return "筹码", "relic"
    if "事件" in cats:
        return "事件", "event"
    # 模板兜底
    if "{{星趴角色" in w:
        return "角色", "char"
    if "{{星趴怪物" in w:
        return "怪物", "monster"
    if "{{星趴筹码" in w:
        return "筹码", "relic"
    if "{{星趴手牌" in w:
        return "卡牌/手牌", "card"
    head = w[:600]
    if "攻击力" in head and "主动技能" in head:
        return "怪物", "monster"
    if "活动" in title or "礼物" in title or "卡池" in title:
        return "活动", "activity"
    return "其他", "other"


def make_chunks(md, pid, title, cat, kind):
    """按 ## / ### 标题切块，保留章节路径。"""
    lines = md.split("\n")
    chunks, cur, path2 = [], [], ""

    def flush():
        body = "\n".join(cur).strip()
        if len(body) < 30:
            return
        prefix = f"# {title}\n分类：{cat}" + (f"\n章节：{path2}" if path2 else "") + "\n\n"
        chunks.append({"id": f"p{pid}:{len(chunks)}", "page_id": pid,
                       "title": title, "category": cat, "kind": kind,
                       "section": path2, "text": prefix + body})

    for line in lines:
        if line.startswith("## "):
            flush()
            cur = [line]
            path2 = line[3:].strip()
            continue
        if line.startswith("### ") and sum(len(x) for x in cur) > 700:
            flush()
            cur = [line]
            path2 = (path2.split(" > ")[0] + " > " + line[4:].strip()
                     if path2 else line[4:].strip())
            continue
        cur.append(line)
    flush()
    return chunks


def summary_of(md, limit=150):
    body = re.sub(r"^#.*$", "", md, flags=re.M)
    body = re.sub(r"^>.*$", "", body, flags=re.M)
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)
    body = re.sub(r"^[#>\-\|\s]+", "", body, flags=re.M)
    body = re.sub(r"\s+", " ", body).strip()
    return body[:limit]


def main():
    os.makedirs(OUT_PAGES, exist_ok=True)
    os.makedirs(OUT_MD, exist_ok=True)
    img = img_index.ImageIndex()
    print(f"本地图片：{len(img.by_name)} 张（按原始文件名归并）", flush=True)

    records = []
    with open(os.path.join(RAW, "pages.jsonl"), encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except Exception:
                pass
    by_title = {norm_title(r["title"]): r for r in records}

    # 子页面（/画廊 /获取 …）合并到角色主页
    alias = {}
    merged = set()
    for r in records:
        t = r["title"]
        for suf in ("/画廊", "/获取", "/筹码搭配"):
            if t.endswith(suf):
                base = t[: -len(suf)]
                base_rec = by_title.get(norm_title(base))
                if base_rec:
                    alias[r["pageid"]] = base_rec["pageid"]
                    merged.add(r["pageid"])

    titles = {}
    for r in records:
        titles[norm_title(r["title"])] = r["pageid"]
    for r in records:
        for l in r.get("links", []):
            nt = norm_title(l)
            if nt not in titles:
                titles[nt] = r["pageid"]
    t2i = {k: alias.get(v, v) for k, v in titles.items()}

    # 先抽取全部页面（子页也要，用于角色档案合并）
    docs, metas = {}, {}
    for r in records:
        pid = r["pageid"]
        docs[pid] = extract_mod.extract(r.get("html", ""), img, t2i, pid)
        if pid in merged:
            continue
        tpl, fields = tpl_fields(r.get("wikitext", ""), r.get("title", ""))
        cat, kind = classify(r, tpl, fields)
        metas[pid] = {"rec": r, "tpl": tpl, "fields": fields, "cat": cat, "kind": kind}
    print(f"解析完成：{len(docs)} 页（合并子页 {len(merged)} 页）", flush=True)

    # 角色富数据
    chars = {}
    for pid, m in metas.items():
        if m["kind"] != "char":
            continue
        title = m["rec"]["title"]
        g = by_title.get(norm_title(title + "/画廊"))
        o = by_title.get(norm_title(title + "/获取"))
        gdoc = docs.get(g["pageid"]) if g else None
        odoc = docs.get(o["pageid"]) if o else None
        try:
            chars[pid] = chargear.build(m["rec"], gdoc, odoc, img)
        except Exception as exc:
            print("  角色解析失败", title, exc, flush=True)
    print(f"角色档案：{len(chars)} 个", flush=True)

    # 生成页面
    index, bundle_pages, all_chunks = [], [], []
    cat_counter = collections.Counter()
    used_thumbs = {}

    # 用模板字段重建结构化正文（筹码/手牌/怪物/事件），比摊平的卡片文字干净
    for pid, m in metas.items():
        layout = tpl_layout.build(m["kind"], m["fields"], m["rec"]["title"])
        if not layout:
            continue
        media = [s for s in docs[pid].get("sections", []) if s.get("title") == "媒体"]
        pics = []
        for s in docs[pid].get("sections", []):
            for b in s["blocks"]:
                if b["t"] == "gal":
                    pics.extend(b["items"])
                elif b["t"] == "fig":
                    pics.append({"name": b["name"], "path": b["path"],
                                 "cap": b["cap"], "kind": b["kind"]})
        if pics:
            layout.append({"level": 2, "title": "图片",
                           "blocks": [{"t": "gal", "items": pics}]})
        docs[pid] = {"sections": layout, "images": docs[pid].get("images", [])}

    for pid, m in metas.items():
        rec, cat, kind = m["rec"], m["cat"], m["kind"]
        title = rec["title"]
        doc = docs[pid]
        char = chars.get(pid)
        source = SOURCE + urllib.parse.quote(title.replace(" ", "_"))

        thumb = ""
        if char:
            thumb = char["head"] or char["portrait"]
        else:
            thumb = pick_thumb(doc, img)
        used_thumbs[pid] = thumb

    for pid, m in metas.items():
        rec, cat, kind = m["rec"], m["cat"], m["kind"]
        title = rec["title"]
        doc = docs[pid]
        char = chars.get(pid)
        source = SOURCE + urllib.parse.quote(title.replace(" ", "_"))
        thumb = used_thumbs.get(pid, "")

        related = []
        seen = set()
        for l in rec.get("links", []):
            rid = t2i.get(norm_title(l))
            if rid and rid != pid and rid in metas and rid not in seen:
                seen.add(rid)
                related.append((rid, metas[rid]["rec"]["title"], metas[rid]["cat"],
                                used_thumbs.get(rid, "")))
            if len(related) >= 8:
                break

        chips = []
        if char:
            pass
        else:
            f = m["fields"]
            for k in ("编号", "品质", "类别", "类型", "时期", "难度", "地图", "尺寸"):
                v = f.get(k)
                if v and len(v) <= 18 and not any(c[0] == k for c in chips):
                    chips.append((k, v))

        opts = {"title": title, "category": cat, "source": source, "thumb": thumb,
                "chips": chips, "related": related, "kind": kind, "char": char,
                "props": [] if (char or m["kind"] in tpl_layout.BUILDERS)
                         else props_for(m["fields"], doc, title, chips),
                "page_id": pid}
        page_html = render_page.render(doc, opts)
        md = render_md.render_md(doc, opts)

        with open(os.path.join(OUT_MD, f"p{pid}.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
        with open(os.path.join(OUT_PAGES, f"p{pid}.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(_shell(title, page_html))

        cat_counter[cat] += 1
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)
        text = re.sub(r"[#>*|`]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        index.append({
            "id": pid, "title": title, "category": cat, "kind": kind,
            "file": f"p{pid}.md", "page": f"p{pid}.html",
            "chars": len(text), "summary": summary_of(md),
            "thumb": thumb, "links": len(rec.get("links", [])),
            "skins": len(char["skins"]) if char else 0,
            "emojis": len(char["emojis"]) if char else 0,
        })
        bundle_pages.append({
            "id": pid, "title": title, "category": cat, "kind": kind,
            "page": f"p{pid}.html", "file": f"p{pid}.md", "thumb": thumb,
            "text": text[:20000], "md": md,
            "skins": [s["name"] for s in char["skins"]] if char else [],
            "emojis": [e["name"] for e in char["emojis"]] if char else [],
        })
        all_chunks += make_chunks(md, pid, title, cat, kind)

    index.sort(key=lambda x: (x["category"], x["title"]))

    # 清理被合并/删除的旧文件，避免查看器打开到过期页面
    keep = {f'p{p["id"]}' for p in index}
    for folder, ext in ((OUT_PAGES, ".html"), (OUT_MD, ".md")):
        for name in os.listdir(folder):
            if not name.endswith(ext):
                continue
            if name[:-len(ext)] not in keep:
                try:
                    os.remove(os.path.join(folder, name))
                except OSError:
                    pass

    cats = [{"name": k, "count": v} for k, v in cat_counter.most_common()]
    known = {c["name"] for c in cats}
    groups = []
    for gname, gcats in GROUPS:
        items = [c for c in cats if c["name"] in gcats]
        if items:
            groups.append({"name": gname, "cats": items,
                           "count": sum(i["count"] for i in items)})
    leftover = [c for c in cats if c["name"] not in
                {x for _, gc in GROUPS for x in gc}]
    if leftover:
        groups.append({"name": "其他", "cats": leftover,
                       "count": sum(c["count"] for c in leftover)})

    stats = {"pages": len(index), "chunks": len(all_chunks),
             "categories": len(cats), "chars": sum(p["chars"] for p in index),
             "characters": len(chars),
             "skins": sum(len(c["skins"]) for c in chars.values()),
             "emojis": sum(len(c["emojis"]) for c in chars.values())}
    with open(os.path.join(DATA, "index.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "source": SOURCE, "stats": stats, "pages": index},
                  f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "chunks.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(os.path.join(DATA, "categories.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"groups": groups, "all": cats}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "characters.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump([{k: v for k, v in c.items() if k != "cosmetics"} | {
            "cosmetics": {kk: [{"name": x["name"], "quality": x.get("quality", ""),
                                "acquire": x.get("acquire", "")} for x in vv]
                          for kk, vv in c["cosmetics"].items() if vv}}
                   for c in chars.values()], f, ensure_ascii=False, indent=1)

    bundle = {"pages": bundle_pages, "stats": stats,
              "groups": groups, "generated_at": time.strftime("%Y-%m-%d %H:%M")}
    with open(os.path.join(DATA, "bundle.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write("window.KB_DATA=" +
                json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
                .replace("<", "\\u003c").replace(">", "\\u003e") + ";")

    print(f"构建完成：{stats['pages']} 页 / {stats['chunks']} 分块 / "
          f"{stats['chars']:,} 字 / {len(cats)} 类", flush=True)
    print(f"角色 {stats['characters']} 个 · 皮肤 {stats['skins']} 套 · "
          f"表情 {stats['emojis']} 个", flush=True)
    print("分类：", cat_counter.most_common(), flush=True)


def _iter_blocks(doc):
    for s in doc.get("sections", []):
        for b in s["blocks"]:
            yield b


def pick_thumb(doc, img):
    """按素材类型的价值挑封面：立绘 > 头像 > 实物图 > 其他。"""
    import img_types
    best, best_score = "", -1
    for name in doc.get("images", []):
        kind = img_types.classify(name)
        if kind == img_types.ICON:
            continue
        w = img_types.KINDS.get(kind, ("", "", 10))[2]
        iw, ih = img.size(name)
        score = w + min((iw * ih) / 200000.0, 8)
        if score > best_score:
            best_score, best = score, name
    return img.local(best) if best else ""


def doc_text(doc):
    out = []
    for b in _iter_blocks(doc):
        for tk in b.get("in") or []:
            if tk[0] in ("t", "b"):
                out.append(tk[1])
        for it in b.get("items") or []:
            for tk in it.get("in") or []:
                if tk[0] in ("t", "b"):
                    out.append(tk[1])
            if isinstance(it, dict) and it.get("v"):
                for tk in it["v"]:
                    if tk[0] in ("t", "b"):
                        out.append(tk[1])
        for row in b.get("rows") or []:
            for cell in row:
                for tk in cell:
                    if tk[0] in ("t", "b"):
                        out.append(tk[1])
    return " ".join(out)


def props_for(fields, doc, title, chips=()):
    """wikitext 里的短字段做成资料卡；正文/顶部给过的信息不再重复。"""
    body = re.sub(r"\s+", "", doc_text(doc))
    shown = {k for k, _ in chips}
    skip = {"描述", "详解", "历史", "花絮", "技能效果", "potential", "皮肤故事"}
    out = []
    for k, v in fields.items():
        if not v or len(v) > 90:
            continue
        if k in shown:
            continue
        if any(k.startswith(s) for s in skip):
            continue
        if re.fullmatch(r"(PVE|皮肤名|皮肤品质|人物传记|礼物|徽章|主动技能|被动技能)\d*", k):
            continue
        v = v.replace("PAGENAME", title)
        key = re.sub(r"\s+", "", v)[:10]
        if key and key in body:
            continue
        out.append((k, v))
        if len(out) >= 10:
            break
    return out


def _shell(title, body):
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{render_page.e(title)}</title>'
        '<link rel="stylesheet" href="../../viewer/page.css"></head><body>'
        + body +
        '<div class="lightbox" id="lightbox" hidden>'
        '<button class="lb-close" aria-label="关闭">×</button>'
        '<button class="lb-prev" aria-label="上一张">‹</button>'
        '<img class="lb-img" alt="">'
        '<button class="lb-next" aria-label="下一张">›</button>'
        '<div class="lb-cap"></div></div>'
        '<script src="../../viewer/page.js"></script></body></html>'
    )


if __name__ == "__main__":
    main()
