#!/usr/bin/env python3
"""把结构化块模型渲染成宽屏、分栏的 HTML 词条页。

设计要点（对应实机反馈的问题）：
- 正文不再是一条竖着排到天边的长条：分节卡片 + 网格 + 右侧锚点栏。
- 角色页是「一站式档案」：概览 / 皮肤（全部套数）/ 表情 / 装扮 / 档案 / 语音，
  用 radio tab 切换，不再把 60 多张图平铺在页面底部。
- 图片带上下文：立绘属于哪套皮肤、表情是第几个，标题写清楚。
"""
import re

import img_types

QUALITY_COLOR = {"绿": "#3fae5a", "蓝": "#3b82f6", "紫": "#a855f7",
                 "橙": "#f59e0b", "红": "#ef4444", "彩": "#ec4899"}
TIER_COLOR = {"绿": "#3fae5a", "蓝": "#3b82f6", "紫": "#a855f7",
              "橙": "#f59e0b", "彩": "#ec4899"}


def e(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def slug(s, fallback="s"):
    s = re.sub(r"[^\w\u4e00-\u9fa5]+", "-", str(s or "")).strip("-")
    return s or fallback


# ---------------------------------------------------------------- 行内
def in_html(tokens):
    out = []
    for tk in tokens:
        k = tk[0]
        if k == "t":
            out.append(e(tk[1]))
        elif k == "b":
            out.append("<b>" + e(tk[1]) + "</b>")
        elif k == "a":
            out.append(f'<a class="kb-link" data-page-id="{tk[2]}">{e(tk[1])}</a>')
        elif k == "img":
            _, name, path, kind, alt = tk
            if not path:
                continue
            label = re.sub(r"\.(png|jpe?g|gif|webp)$", "", alt or name)
            out.append(f'<img class="ic" src="{e(path)}" alt="{e(label)}" loading="lazy">')
        elif k == "imginline":
            _, name, path, kind, alt = tk
            if not path:
                continue
            label = re.sub(r"\.(png|jpe?g|gif|webp)$", "", alt or name)
            out.append(f'<img class="fig-inline" src="{e(path)}" alt="{e(label)}" loading="lazy">')
    s = "".join(out)
    s = re.sub(r"(<br>\s*){3,}", "<br><br>", s)
    return s.strip()


def plain(tokens, link_style="md"):
    out = []
    for tk in tokens:
        k = tk[0]
        if k in ("t", "b"):
            out.append(tk[1])
        elif k == "a":
            if link_style == "md":
                out.append(f"[{tk[1]}](p{tk[2]}.md)")
            else:
                out.append(tk[1])
        elif k in ("img", "imginline"):
            pass
    return re.sub(r"\s+", " ", "".join(out)).strip()


def imgs_of(tokens):
    return [tk for tk in tokens if tk[0] in ("img", "imginline")]


# ---------------------------------------------------------------- 块
def block_html(b, opts):
    t = b["t"]
    if opts.get("skip") is b:
        return ""
    if t == "p":
        body = in_html(b["in"])
        if not body:
            return ""
        extra = ""
        big = [x for x in b["in"] if x[0] == "imginline"]
        if big:
            extra = '<div class="figrow">' + "".join(
                f'<figure class="shot sm"><img src="{e(x[2])}" alt="{e(x[4])}" loading="lazy">'
                f'<figcaption>{e(re.sub(r"\.(png|jpe?g|gif|webp)$", "", x[4] or x[1]))}</figcaption></figure>'
                for x in big) + "</div>"
            body = in_html([x for x in b["in"] if x[0] != "imginline"])
        return f'<p>{body}</p>{extra}'
    if t == "pre":
        return f"<pre>{e(b['text'])}</pre>"
    if t == "ul":
        return ul_html(b["items"])
    if t == "dl":
        return dl_html(b["items"])
    if t == "table":
        return table_html(b, opts)
    if t == "gal":
        return gallery_html(b["items"], opts)
    if t == "pass":
        return pass_html(b["rows"])
    if t == "fig":
        if opts.get("thumb") and b["path"] == opts["thumb"]:
            return ""      # 与顶部大图重复
        return (f'<figure class="shot"><img src="{e(b["path"])}" alt="{e(b["cap"] or b["name"])}" loading="lazy">'
                f'<figcaption>{e(b["cap"] or opts.get("title") or pretty_name(b["name"]))}</figcaption></figure>')
    return ""


def pretty_name(name):
    s = re.sub(r"\.(png|jpe?g|gif|webp)$", "", name or "")
    s = re.sub(r"^UT[_ ]", "", s, flags=re.I).replace("_", " ")
    return s


def ul_html(items):
    out, stack = [], []
    for it in items:
        lv = it.get("lv", 0)
        while len(stack) > lv:
            out.append("</li></ul>")
            stack.pop()
        if len(stack) == lv:
            if stack:
                out.append("</li>")
            out.append("<ul>")
            stack.append(1)
        elif len(stack) < lv:
            out.append("<ul>")
            stack.append(1)
        out.append("<li>" + in_html(it["in"]))
    while stack:
        out.append("</li></ul>")
        stack.pop()
    return "".join(out)


def dl_html(items):
    out = ['<dl class="kv">']
    for it in items:
        out.append(f'<dt>{in_html(it["k"])}</dt><dd>{in_html(it["v"])}</dd>')
    out.append("</dl>")
    return "".join(out)


def table_html(b, opts):
    head, rows, imgs = b.get("head") or [], b["rows"], b.get("imgs") or []
    first_h = plain(head[0]) if head else ""
    # 装扮类表格：有物品图 -> 卡片网格
    if imgs and head and ("物品" in first_h or "图片" in first_h):
        name_i = 1 if len(head) > 1 else 0
        desc_i = 2 if len(head) > 3 else -1
        acq_i = len(head) - 1
        cards = []
        for i, row in enumerate(rows):
            im = imgs[i] if i < len(imgs) else {}
            nm = plain(row[name_i]) if name_i < len(row) else ""
            acq = plain(row[acq_i]) if acq_i < len(row) else ""
            desc = plain(row[desc_i]) if 0 <= desc_i < len(row) else ""
            if desc == nm:
                desc = ""
            q = (im or {}).get("quality", "")
            ring = QUALITY_COLOR.get(q, "")
            style = f' style="--q:{ring}"' if ring else ""
            pic = (f'<img src="{e(im["path"])}" alt="{e(nm)}" loading="lazy">'
                   if im and im.get("path") else '<span class="ph">?</span>')
            cards.append(
                f'<figure class="item"{style}><div class="item-img">{pic}</div>'
                f'<figcaption><b>{e(nm)}</b>'
                + (f'<i class="qtag">{e(q)}</i>' if q else "")
                + (f'<span class="desc">{e(desc)}</span>' if desc else "")
                + (f'<span class="acq">{e(acq)}</span>' if acq else "")
                + "</figcaption></figure>")
        return '<div class="items">' + "".join(cards) + "</div>"

    w = max([len(head)] + [len(r) for r in rows]) if rows else 0
    out = ['<div class="table-wrap"><table>']
    if head:
        out.append("<thead><tr>" + "".join(f"<th>{in_html(c)}</th>" for c in head) + "</tr></thead>")
    out.append("<tbody>")
    for row in rows:
        cells = list(row) + [[]] * (w - len(row))
        out.append("<tr>" + "".join(
            f"<td>{in_html([t for t in c if t[0] != 'img'])}</td>" for c in cells) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


PASS_TRACKS = ("免费", "付费", "付费+升级")


def pass_html(rows):
    """通行证奖励墙 -> 等级 ×（免费 / 付费 / 付费+升级）表。"""
    out = ['<div class="table-wrap"><table class="pass"><thead><tr>'
           '<th style="width:64px">等级</th>'
           + "".join(f'<th class="tr{"-free" if i == 0 else ""}">{t}</th>'
                     for i, t in enumerate(PASS_TRACKS))
           + '</tr></thead><tbody>']
    for r in rows:
        tds = []
        for i in range(len(PASS_TRACKS)):
            a = r["awards"][i] if i < len(r["awards"]) else None
            if not a:
                tds.append('<td class="empty">—</td>')
                continue
            q = QUALITY_COLOR.get(a.get("quality", ""), "")
            pic = (f'<img src="{e(a["path"])}" alt="" loading="lazy" style="--q:{q}">'
                   if a.get("path") else "")
            tds.append(f'<td><span class="rw">{pic}<i>{e(a.get("num", ""))}</i></span></td>')
        out.append(f'<tr><td class="lv">{e(r["level"])}</td>' + "".join(tds) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def gallery_html(items, opts):
    out = ['<div class="gallery">']
    for it in items:
        if not it.get("path"):
            continue
        cap = it.get("cap") or pretty_name(it["name"])
        out.append(f'<figure class="shot"><img src="{e(it["path"])}" alt="{e(cap)}" loading="lazy">'
                   f'<figcaption>{e(cap)}</figcaption></figure>')
    out.append("</div>")
    return "".join(out) if len(out) > 2 else ""


# ---------------------------------------------------------------- 页面骨架
def hero_html(title, cat, source, lead, thumb, chips, kind=""):
    out = ['<header class="hero%s">' % (" has-art" if thumb else "")]
    out.append('<div class="hero-art">' +
               (f'<img src="{e(thumb)}" alt="{e(title)}">' if thumb
                else f'<span class="ph">{e(title[:1])}</span>') + "</div>")
    out.append('<div class="hero-info">')
    out.append('<div class="hero-eyebrow">' +
               f'<span class="badge">{e(cat)}</span>' +
               (f'<a class="origin" href="{e(source)}" target="_blank" rel="noopener">官方原文 ↗</a>' if source else "") +
               "</div>")
    out.append(f"<h1>{e(title)}</h1>")
    if lead:
        out.append(f'<p class="lead">{in_html(lead) if isinstance(lead, list) else e(lead)}</p>')
    if chips:
        out.append('<div class="chips">' + "".join(
            f'<span class="chip"><i>{e(k)}</i>{e(v)}</span>' for k, v in chips) + "</div>")
    out.append("</div></header>")
    return "".join(out)


def toc_html(items):
    """items: [(anchor_id, title)]，只列真正渲染出来的小节。"""
    if len(items) < 3:
        return ""
    out = ['<aside class="rail"><div class="rail-in"><div class="rail-t">本页目录</div><nav>']
    for sid, t in items:
        out.append(f'<a href="#{sid}">{e(t)}</a>')
    out.append("</nav></div></aside>")
    return "".join(out)


def sections_html(sections, opts, collect=None):
    """通用正文渲染：跳过纯目录/空节，空内容不产生空白卡片。"""
    out = []
    for i, s in enumerate(sections):
        if not s["blocks"] or s["title"] in ("目录", "视频"):
            continue
        body = "".join(block_html(b, opts) for b in s["blocks"]).strip()
        if not body:
            continue
        sid = f"sec{i}"
        lv = s["level"]
        if lv <= 2:
            cls = "sec no-title" if not s["title"] else "sec"
            out.append(f'<section class="{cls}" id="{sid}">'
                       + (f'<h2>{e(s["title"])}</h2>' if s["title"] else ""))
        elif lv == 3:
            out.append(f'<section class="sec sub" id="{sid}"><h3>{e(s["title"])}</h3>')
        elif lv == 4:
            out.append(f'<h4 class="sub4">{e(s["title"])}</h4>')
        else:
            out.append(f'<h5 class="sub5">{e(s["title"])}</h5>')
        out.append(body)
        if lv <= 3:
            out.append("</section>")
        if collect is not None and s["title"]:
            collect.append((sid, s["title"]))
    return "".join(out)


def related_html(related):
    if not related:
        return ""
    out = ['<section class="sec"><h2>相关内容</h2><div class="rel-grid">']
    for rid, rtitle, rcat, rthumb in related:
        out.append(
            f'<a class="rel" data-page-id="{rid}" href="#">'
            f'<span class="rel-img">' +
            (f'<img src="{e(rthumb)}" alt="">' if rthumb else e(rtitle[:1])) +
            f'</span><span class="rel-t">{e(rtitle)}</span>'
            f'<span class="rel-c">{e(rcat)}</span></a>')
    out.append("</div></section>")
    return "".join(out)


# ---------------------------------------------------------------- 角色富页面
def tab_radios(name, labels, prefix):
    out = []
    for i, (lab, cnt) in enumerate(labels):
        checked = " checked" if i == 0 else ""
        out.append(f'<input class="tabin" type="radio" name="{name}" id="{prefix}{i}"{checked}>')
        out.append(f'<label class="tabl" for="{prefix}{i}">{e(lab)}'
                   + (f'<span class="n">{cnt}</span>' if cnt != "" else "") + "</label>")
    return "".join(out)


def render_char(c, opts):
    """角色一站式档案页。"""
    name = c["name"]
    skins = c["skins"]
    emojis = c["emojis"]
    cos = c["cosmetics"]
    n_cos = sum(len(cos[k]) for k in ("头像", "名片", "卡牌", "骰子", "主页背景"))

    lead = c["bio"][0] if c["bio"] else ""
    lead = re.sub(r"\s+", "", lead)[:150]
    chips = []
    if c["number"]:
        chips.append(("编号", c["number"]))
    if c["period"]:
        chips.append(("时期", c["period"]))
    if c["gender"]:
        chips.append(("性别", c["gender"]))
    if c["birthday"]:
        chips.append(("生日", c["birthday"]))
    if c["org"]:
        chips.append(("组织", c["org"]))
    if c["food"]:
        chips.append(("喜欢", c["food"]))

    out = ['<article class="page char">']
    out.append(hero_html(name + (f" · {c['title']}" if c["title"] else ""),
                         "角色", opts.get("source", ""), lead, c["portrait"], chips))
    out.append('<div class="wrap">')

    # 战斗数值条
    if c["stats"]:
        out.append('<div class="stats">' + "".join(
            f'<div class="stat"><span>{e(s["k"])}</span><b>{e(s["v"])}</b></div>'
            for s in c["stats"]) + "</div>")

    tabs = [("概览", ""), ("皮肤", len(skins)), ("表情", len(emojis)),
            ("装扮", n_cos or ""), ("档案", ""), ("语音", len(c["voices"]) or "")]
    out.append('<div class="tabs">')
    out.append(tab_radios("main", tabs, "m"))
    out.append('<div class="panes">')

    # ---- 概览 ----
    out.append('<div class="pane">')
    if c["skills"]:
        out.append('<div class="skill-grid">')
        for s in c["skills"]:
            out.append(
                f'<div class="skill"><div class="skill-h"><span class="kind">{e(s["kind"])}</span>'
                f'<b>{e(s["name"])}</b>'
                + (f'<span class="cd">冷却 {e(s["cd"])}</span>' if s["cd"] else "") +
                f'</div><p>{e(s["desc"]) or "—"}</p>'
                + (f'<p class="pve"><b>PVE</b>{e(s["pve"])}</p>' if s.get("pve") else "")
                + '</div>')
        out.append("</div>")
    extra = []
    if c["potential"]:
        extra.append(
            f'<div class="note"><div class="note-t">潜能激发</div><p>{e(c["potential"])}</p></div>')
    if c["skill_note"]:
        extra.append(
            f'<div class="note"><div class="note-t">技能细节</div><p>{e(c["skill_note"])}</p></div>')
    if extra:
        out.append('<div class="note-grid">' + "".join(extra) + "</div>")

    kv = []
    for k, v in (("姓名", c["full_name"]), ("英文名", c["en"]), ("日文名", c["jp"]),
                 ("从属组织", c["org"]), ("事件经历", c["event"]),
                 ("上线时间", _date(c["released"])), ("喜欢食物", c["food"]),
                 ("初始骰子", c["dice"]), ("礼物", "、".join(c["gifts"])),
                 ("徽章", "、".join(c["badges"]))):
        if v:
            kv.append(f'<div class="kvi"><span>{e(k)}</span><b>{e(v)}</b></div>')
    if kv:
        out.append('<h3 class="sub">基础资料</h3><div class="kv-grid">' + "".join(kv) + "</div>")
    if c["pve"]:
        out.append('<h3 class="sub">PVE 特性</h3><ul class="dots">' +
                   "".join(f"<li>{e(x)}</li>" for x in c["pve"]) + "</ul>")
    out.append("</div>")

    # ---- 皮肤 ----
    out.append('<div class="pane">')
    out.append(_skins_html(skins, c))
    out.append("</div>")

    # ---- 表情 ----
    out.append('<div class="pane">')
    out.append(_emojis_html(emojis))
    out.append("</div>")

    # ---- 装扮 ----
    out.append('<div class="pane">')
    out.append(_cosmetics_html(cos, c))
    out.append("</div>")

    # ---- 档案 ----
    out.append('<div class="pane">')
    out.append(_archive_html(c, skins, lead))
    out.append("</div>")

    # ---- 语音 ----
    out.append('<div class="pane">')
    out.append(_voice_html(c["voices"]))
    out.append("</div>")

    out.append("</div></div>")      # panes / tabs
    out.append(related_html(opts.get("related") or []))
    out.append("</div></article>")
    return "".join(out)


def _date(s):
    s = (s or "").strip()
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else s


def _skins_html(skins, c):
    if not skins:
        return '<p class="empty">本地未收录该角色的皮肤数据。</p>'
    out = ['<div class="skins">']
    # radio 输入必须是 .skin-tabs 与 .skin-panes 的共同前序兄弟，CSS 才能用 ~ 选中
    for i in range(len(skins)):
        out.append(f'<input class="tabin" type="radio" name="skin" id="sk{i}"'
                   + (' checked' if i == 0 else '') + '>')
    out.append('<div class="skin-tabs">')
    for i, sk in enumerate(skins):
        thumb = (sk["imgs"].get("head") or sk["imgs"].get("art") or {}).get("path", "")
        badge = sk.get("tier", "") if sk["kind"] == "skin" else ""
        out.append(
            f'<label class="skin-tab" for="sk{i}" title="{e(sk["name"])}">'
            f'<span class="st-img">' + (f'<img src="{e(thumb)}" alt="">' if thumb else "")
            + '</span><span class="st-n">' + e(sk["name"]) + "</span>"
            + (f'<i class="st-q" style="--q:{TIER_COLOR.get(badge, "#94a3b8")}">{e(badge)}</i>' if badge else "")
            + "</label>")
    out.append("</div>")
    out.append('<div class="skin-panes">')
    for i, sk in enumerate(skins):
        out.append(f'<div class="skin-pane p{i}">')
        art = sk["imgs"].get("art") or {}
        art_sfw = sk["imgs"].get("art_sfw") or {}
        out.append('<div class="skin-hero">')
        # 立绘：原版 + 和谐版横向并排
        duo = " duo" if (art.get("path") and art_sfw.get("path")) else ""
        out.append(f'<div class="skin-arts{duo}">')
        if art.get("path"):
            out.append(f'<figure class="shot tall"><img src="{e(art["path"])}" alt="{e(sk["name"])}立绘" loading="lazy">'
                       f'<figcaption>{e(sk["name"])} 立绘</figcaption></figure>')
        if art_sfw.get("path"):
            out.append(f'<figure class="shot tall"><img src="{e(art_sfw["path"])}" alt="{e(sk["name"])}和谐版立绘" loading="lazy">'
                       f'<figcaption>{e(sk["name"])} 和谐版</figcaption></figure>')
        if not art.get("path") and not art_sfw.get("path"):
            out.append('<div class="ph big">暂无立绘</div>')
        out.append("</div>")
        # 信息 + 变体 + 故事：始终在右侧，不压住立绘
        out.append('<div class="skin-side">')
        out.append(f'<h3>{e(sk["name"])}</h3>')
        meta = []
        if sk.get("tier"):
            meta.append(f'<span class="tag" style="--q:{TIER_COLOR.get(sk["tier"],"#94a3b8")}">{e(sk["tier"])}品质</span>')
        if sk["kind"] == "default":
            meta.append('<span class="tag">初始皮肤</span>')
        if sk["kind"] == "bond":
            meta.append('<span class="tag">羁绊解锁</span>')
        if sk.get("code"):
            meta.append(f'<span class="tag mono">{e(sk["code"])}</span>')
        if meta:
            out.append('<div class="tags">' + "".join(meta) + "</div>")
        if sk.get("acquire"):
            out.append(f'<p class="acq"><b>获取方式</b>{e(sk["acquire"])}</p>')
        variants = [(k, v) for k, v in sk["imgs"].items()
                    if k not in ("art", "art_sfw") and v.get("path")]
        order = ["head", "headq", "chibi", "bust_low", "bust_high", "nameplate"]
        variants.sort(key=lambda x: order.index(x[0]) if x[0] in order else 99)
        if variants:
            out.append('<div class="variants">')
            for k, v in variants:
                out.append(f'<figure class="shot xs"><img src="{e(v["path"])}" alt="{e(img_types.SLOT_LABEL.get(k, k))}" loading="lazy">'
                           f'<figcaption>{e(img_types.SLOT_LABEL.get(k, k))}</figcaption></figure>')
            out.append("</div>")
        if sk.get("story"):
            out.append('<div class="story-block"><div class="story-t">皮肤故事</div>'
                       f'<p>{e(sk["story"])}</p></div>')
        out.append("</div></div></div>")
    out.append("</div></div>")
    return "".join(out)


def _emojis_html(emojis):
    if not emojis:
        return '<p class="empty">本地未收录该角色的表情。</p>'
    out = [f'<p class="hint">共 {len(emojis)} 个表情，点击可放大。</p><div class="emoji-grid">']
    for em in emojis:
        q = em.get("quality", "")
        out.append(
            f'<figure class="emoji" style="--q:{QUALITY_COLOR.get(q, "#cbd5e1")}">'
            f'<img src="{e(em["img"])}" alt="{e(em["name"])}" loading="lazy">'
            f'<figcaption><b>{e(em["name"])}</b>'
            + (f'<span class="acq">{e(em["acquire"])}</span>' if em.get("acquire") else "")
            + "</figcaption></figure>")
    out.append("</div>")
    return "".join(out)


COS_LABEL = {"头像": "头像", "名片": "名片", "卡牌": "卡牌", "骰子": "骰子", "主页背景": "主页背景"}


def _cosmetics_html(cos, c):
    parts = []
    for key, label in COS_LABEL.items():
        rows = cos.get(key) or []
        if not rows:
            continue
        cards = []
        for r in rows:
            q = r.get("quality", "")
            pic = (f'<img src="{e(r["img"])}" alt="{e(r["name"])}" loading="lazy">'
                   if r.get("img") else '<span class="ph">?</span>')
            cards.append(
                f'<figure class="item" style="--q:{QUALITY_COLOR.get(q, "")}">'
                f'<div class="item-img">{pic}</div><figcaption><b>{e(r["name"])}</b>'
                + (f'<i class="qtag">{e(q)}</i>' if q else "")
                + (f'<span class="acq">{e(r["acquire"])}</span>' if r.get("acquire") else "")
                + "</figcaption></figure>")
        parts.append(f'<div class="cos-group"><h3 class="sub">{label}'
                     f'<span class="cnt">{len(rows)}</span></h3>'
                     f'<div class="items">' + "".join(cards) + "</div></div>")
    if not parts:
        parts.append('<p class="empty">官方 wiki 没有这角色的 /获取 页，'
                     '头像、名片、卡牌、骰子的完整清单暂缺；'
                     '下方「档案」里保留了画廊中的零散素材。</p>')
    return "".join(parts)


def _archive_html(c, skins, lead=""):
    out = []
    bio = c["bio"]
    if bio and lead:
        key = re.sub(r"\s+", "", lead)[:20]
        if key and re.sub(r"\s+", "", bio[0]).startswith(key):
            bio = bio[1:]
    if bio:
        out.append('<h3 class="sub">人物传记</h3>')
        for p in bio:
            out.append(f'<p class="prose">{e(p)}</p>')
    stories = [(s["name"], s["story"]) for s in skins if s.get("story")]
    if stories:
        out.append('<h3 class="sub">皮肤故事</h3>')
        for nm, st in stories:
            out.append(f'<details class="story"><summary>{e(nm)}</summary><p>{e(st)}</p></details>')
    if c["others"]:
        out.append('<h3 class="sub">画廊其他素材</h3><div class="gallery">')
        for o in c["others"]:
            out.append(f'<figure class="shot sm"><img src="{e(o["path"])}" alt="{e(o["cap"])}" loading="lazy">'
                       f'<figcaption>{e(o["cap"])}</figcaption></figure>')
        out.append("</div>")
    return "".join(out) or '<p class="empty">暂无档案内容。</p>'


def _voice_html(voices):
    if not voices:
        return '<p class="empty">本地未收录该角色的语音台词。</p>'
    out = [f'<p class="hint">共 {len(voices)} 条中文语音台词（日文台词在官方 wiki 的语音页）。</p>',
           '<div class="table-wrap"><table><thead><tr><th style="width:96px">场景</th>'
           '<th>台词</th></tr></thead><tbody>']
    for v in voices:
        out.append(f'<tr><td class="scene">{e(v["scene"])}</td><td>{e(v["text"])}</td></tr>')
    out.append("</tbody></table></div>")
    return "".join(out)


# ---------------------------------------------------------------- 通用页面
def props_html(props):
    if not props:
        return ""
    items = "".join(
        f'<div class="kvi"><span>{e(k)}</span><b>{inline_or_text(v)}</b></div>'
        for k, v in props)
    return f'<section class="sec"><h2>词条资料</h2><div class="kv-grid">{items}</div></section>'


def inline_or_text(v):
    return e(v)


def render_generic(doc, opts):
    title = opts.get("title", "")
    cat = opts.get("category", "")
    source = opts.get("source", "")
    thumb = opts.get("thumb", "")
    sections = doc.get("sections", [])

    lead = ""
    lead_block = None
    # 导语取第一节的第一段；太短或不在首节时只借用、不从正文删除
    first_sec = next((s for s in sections if s["blocks"]), None)
    if first_sec:
        first_p = next((b for b in first_sec["blocks"] if b["t"] == "p"), None)
        if first_p is not None and len(plain(first_p["in"], "plain")) >= 6:
            txt = plain(first_p["in"], "plain")
            lead = txt if len(txt) <= 120 else txt[:112].rstrip() + "…"
            # 只有该节仅此一段时才从正文移除，避免把「仅剩一条」的章节掏空
            if len(first_sec["blocks"]) == 1:
                lead_block = first_p
        else:
            for s in sections:
                for b in s["blocks"]:
                    if b["t"] == "p":
                        txt = plain(b["in"], "plain")
                        if len(txt) > 20:
                            lead = txt if len(txt) <= 120 else txt[:112].rstrip() + "…"
                            break
                if lead:
                    break
    # 短导语：正文里不再重复；长导语：正文保留全文
    opts_skip = dict(opts)
    if lead_block is not None and len(plain(lead_block["in"], "plain")) <= 120:
        opts_skip["skip"] = lead_block

    chips = opts.get("chips") or []
    out = ['<article class="page">']
    out.append(hero_html(title, cat, source, lead, thumb, chips))
    used = []
    main = sections_html(sections, opts_skip, used)
    rail = toc_html(used)
    out.append('<div class="doc%s">' % ("" if rail else " no-rail"))
    out.append('<main class="doc-main">')
    out.append(props_html(opts.get("props") or []))
    out.append(main)
    out.append(related_html(opts.get("related") or []))
    out.append("</main>")
    if rail:
        out.append(rail)
    out.append("</div></article>")
    return "".join(out)


def render(doc, opts):
    if opts.get("char"):
        return render_char(opts["char"], opts)
    return render_generic(doc, opts)
