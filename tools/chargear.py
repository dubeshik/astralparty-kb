#!/usr/bin/env python3
"""构建角色档案：把「角色页 + /画廊 + /获取」三份数据合成一个完整模型。

关键点：
- 皮肤不是 4 套，而是「默认 + 羁绊皮肤 + 皮肤名1..N」（芬妮 = 6 套）。
- 每套皮肤的立绘/头像/Q版/半身像按画廊里 h5 分组归类，不再混成一堆图。
- /获取 页的表格提供名称、品质、获取方式，按素材编号与画廊图片对齐。
"""
import html as _html
import re

import img_types

SKIN_TIER = {
    "emerald": ("绿", 1), "sapphire": ("蓝", 2), "amethyst": ("紫", 3),
    "platinum": ("橙", 4), "ultimate": ("彩", 5),
}
QUALITY_COLOR = {"绿": "#4caf50", "蓝": "#3b82f6", "紫": "#a855f7",
                 "橙": "#f59e0b", "红": "#ef4444", "彩": "#ec4899", "": "#94a3b8"}


def tier_of(q):
    return SKIN_TIER.get((q or "").strip().lower(), ("", 0))


def clean(v, title=""):
    """wikitext → 纯文本：展开嵌套模板、保留链接文字、去注释。"""
    v = re.sub(r"<!--[\s\S]*?-->", "", v or "")
    v = re.sub(r"<br\s*/?>", "\n", v, flags=re.I)
    if title:
        v = re.sub(r"\{\{\s*PAGENAME\s*\}\}", title, v, flags=re.I)
    # 由内向外反复展开 {{模板|参数...}}
    for _ in range(10):
        new = re.sub(r"\{\{([^{}|]*)\|([^{}]*)\}\}", _expand_tpl, v)
        if new == v:
            break
        v = new
    v = re.sub(r"\[\[(?:file|File|文件):[^\]]*\|link=[^\]]*\]\]", "", v)
    v = re.sub(r"\[\[(?:file|File|文件):[^\]]*\]\]", "", v)
    v = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", v)
    v = re.sub(r"\[\[([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"\{\{[^{}]*\}\}", "", v)
    v = v.replace("'''", "").replace("''", "")
    v = re.sub(r"[ \t]+", " ", v)
    v = re.sub(r"\n{3,}", "\n\n", v)
    return v.strip()


def _expand_tpl(m):
    """{{Buff|金鳞|130 1|说明}} 取名字；{{有色文字|色|文字}} 取文字。"""
    name = m.group(1).strip()
    args = m.group(2).split("|")
    low = name.lower()
    if low == "buff" or "图标" in name or name.startswith("状态"):
        head = args[0].strip()
        note = ""
        if len(args) >= 3:
            note = re.sub(r"<br\s*/?>", "，", args[2])
            note = re.sub(r"\s+", "", note)[:20]
        return head + (f"（{note}）" if note else "")
    return args[-1].strip()


def tpl_fields(wikitext, title=""):
    """取页面里第一个模板的 key=value（模板不一定在页首，前面可能有提示框）。"""
    s = (wikitext or "")
    m = re.search(r"\{\{\s*[^\s|}{]+", s)
    if not m:
        return "", {}
    s = s[m.start():]
    if s[2:3] == "#":        # {{#widget:…}} {{#css:…}} 之类，不是数据模板
        return "", {}
    depth, i, end = 0, 0, None
    while i < len(s) - 1:
        if s[i:i + 2] == "{{":
            depth += 1
            i += 2
            continue
        if s[i:i + 2] == "}}":
            depth -= 1
            if depth == 0:
                end = i
                break
            i += 2
            continue
        i += 1
    if end is None:
        return "", {}
    body = s[2:end]
    name = body.split("|", 1)[0].strip()
    fields = {}
    # 按顶层 | 切分
    parts, buf, d, wd = [], [], 0, 0
    i = 0
    while i < len(body):
        two = body[i:i + 2]
        if two == "{{":
            d += 1
            buf.append(two)
            i += 2
            continue
        if two == "}}":
            d = max(0, d - 1)
            buf.append(two)
            i += 2
            continue
        if two == "[[":
            wd += 1
            buf.append(two)
            i += 2
            continue
        if two == "]]":
            wd = max(0, wd - 1)
            buf.append(two)
            i += 2
            continue
        if body[i] == "|" and d == 0 and wd == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(body[i])
        i += 1
    parts.append("".join(buf))
    for p in parts[1:]:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        k = re.sub(r"\s+", "", k)
        if k:
            fields[k] = clean(v, title)
    return name, fields


def _skin_code(name, num):
    """从素材文件名推出皮肤编号：UT_Hero_Card_102_01 -> 102_01"""
    if not name or not num:
        return ""
    m = re.search(rf"_{re.escape(str(num))}((?:_[A-Za-z0-9]+)*)\.(?:png|jpe?g|gif|webp)$",
                  name, re.I)
    if not m:
        return ""
    tail = m.group(1)
    if tail in ("_0", "_1"):        # 半身像的 0/1 序号，不是皮肤
        return str(num)
    return str(num) + tail


def _emoji_code(name, num):
    code = _skin_code(name, num)
    if not code:
        return ""
    prefix = str(num)
    return code[len(prefix) + 1:] if code.startswith(prefix + "_") else code


def _items_of(section):
    out = []
    for b in section.get("blocks", []):
        if b["t"] == "gal":
            out.extend(b["items"])
        elif b["t"] == "fig":
            out.append({"name": b["name"], "path": b["path"],
                        "cap": b["cap"], "kind": b["kind"]})
    return out


def _slot(item):
    s = img_types.slot_of(item.get("cap"))
    if s:
        return s
    k = item.get("kind")
    return {"art": "art", "art_sfw": "art_sfw", "chibi": "chibi", "head": "head",
            "headq": "headq", "bust": "bust", "nameplate": "nameplate",
            "platform": "platform", "rolephoto": "rolephoto",
            "headshot": "headshot", "reward": "reward", "kv": "kv"}.get(k, k)


def parse_voice(raw_html):
    """角色页里内嵌的中文语音表（textarea#CNInfoInput）。"""
    m = re.search(r'<textarea[^>]*id="CNInfoInput"[^>]*>([\s\S]*?)</textarea>',
                  raw_html or "", re.I)
    if not m:
        return []
    body = _html.unescape(m.group(1))
    rows = []
    for line in body.split("\n"):
        line = line.strip()
        if not line or line.count("$") < 2:
            continue
        scene, text, _ = line.split("$", 2)
        scene = clean(scene).replace("\n", " ")
        text = re.sub(r"<br\s*/?>", " / ", text)
        text = clean(text.replace("&&", " / ")).replace("\n", " ")
        if scene and text and not text.startswith("http"):
            rows.append({"scene": scene, "text": text})
    return rows


def build(char_rec, gallery_rec, obtain_rec, img):
    """返回角色模型 dict。"""
    wtext = (char_rec or {}).get("wikitext", "")
    tpl, f = tpl_fields(wtext)
    name = f.get("中文名") or (char_rec or {}).get("title", "")
    num = f.get("编号", "")

    stats = []
    for k, label in (("攻", "攻击"), ("防", "防御"), ("血", "生命")):
        v = f.get(k, "")
        if v and v not in ("-", "—"):
            stats.append({"k": label, "v": v})

    skills = []
    for kind, key, cd, desc in (("主动", "主动技能", "主动技能冷却", "主动技能描述"),
                                ("被动", "被动技能", "", "被动技能描述")):
        if f.get(key):
            skills.append({"kind": kind, "name": f[key],
                           "cd": f.get(cd, ""), "desc": f.get(desc, "")})
    # PVE 版技能描述单独保留
    for s in skills:
        pve = f.get(f"{s['kind']}技能PVE描述", "")
        s["pve"] = "" if pve and pve == s["desc"] else pve
    if f.get("被动技能2PVE"):
        skills.append({"kind": "被动", "name": f["被动技能2PVE"], "cd": "",
                       "desc": f.get("被动技能2PVE描述", ""), "pve": "",
                       "extra": "PVE"})

    # ---- 皮肤 ----
    skin_names = []
    for i in range(1, 9):
        nm = f.get(f"皮肤名{i}")
        if nm:
            skin_names.append((nm, f.get(f"皮肤品质{i}", ""), f.get(f"皮肤故事{i}", "")))

    skins, emojis, others = [], [], []
    if gallery_rec:
        secs = gallery_rec.get("sections", [])
        mode, cur = None, None
        for s in secs:
            lv, title = s["level"], s["title"]
            if lv <= 2:
                mode, cur = None, None
                continue
            if lv == 3:
                cur = None
                mode = ("emoji" if "表情" in title else
                        "skin" if "皮肤" in title else
                        "other" if "其他" in title else None)
                if mode is None:
                    continue
                if mode == "other":
                    others.extend(_items_of(s))
                if mode == "emoji":
                    emojis.extend(_items_of(s))
                continue
            if lv >= 4 and mode == "skin":
                items = _items_of(s)
                if not items:
                    continue
                cv = {}
                for it in items:
                    code = _skin_code(it["name"], num)
                    if code:
                        cv[code] = cv.get(code, 0) + 1
                code = max(cv, key=cv.get) if cv else ""
                skins.append({"code": code, "name": title, "items": items})
            elif lv >= 4 and mode == "other":
                others.extend(_items_of(s))

    # 画廊缺失时用模板皮肤名兜底
    if not skins and skin_names:
        skins = [{"code": "", "name": nm, "items": []} for nm, _, _ in skin_names]

    # 名称/品质/故事对齐
    by_name = {nm: (q, story) for nm, q, story in skin_names}
    for i, sk in enumerate(skins):
        nm = sk["name"]
        if nm in by_name:
            sk["quality"], sk["story"] = by_name[nm]
        else:
            sk["quality"], sk["story"] = "", ""
        if nm in ("默认",) or not nm:
            sk["kind"] = "default"
            sk["quality"] = ""
        elif "羁绊" in nm:
            sk["kind"] = "bond"
        else:
            sk["kind"] = "skin"
        # 槽位归类
        slots = {}
        for it in sk.pop("items", []):
            sl = _slot(it)
            if sl and sl not in slots:
                slots[sl] = {"name": it["name"], "path": it["path"], "cap": it["cap"]}
        sk["imgs"] = slots
        sk["tier"], sk["tierRank"] = tier_of(sk.get("quality", ""))
        sk["acquire"] = ""

    # 模板里有、画廊里没有的皮肤也补上
    have = {s["name"] for s in skins}
    for nm, q, story in skin_names:
        if nm not in have:
            t, r = tier_of(q)
            skins.append({"code": "", "name": nm, "kind": "skin", "quality": q,
                          "story": story, "imgs": {}, "tier": t, "tierRank": r,
                          "acquire": ""})

    # ---- /获取 表格：名称 + 品质 + 获取方式 ----
    cosmetics = {"头像": [], "名片": [], "卡牌": [], "骰子": [], "主页背景": [], "表情": [], "皮肤": [], "角色": []}
    if obtain_rec:
        cur_sec = ""
        for s in obtain_rec.get("sections", []):
            if s["level"] == 2 and s["title"]:
                cur_sec = s["title"].strip()
            for b in s["blocks"]:
                if b["t"] != "table":
                    continue
                rows, imgs = b["rows"], b.get("imgs") or []
                for ri, row in enumerate(rows):
                    cells = ["".join(t[1] for t in c if t[0] in ("t", "b", "a")).strip() for c in row]
                    nm = cells[1] if len(cells) > 1 else ""
                    acq = cells[2] if len(cells) > 2 else ""
                    im = imgs[ri] if ri < len(imgs) else {"path": "", "name": "", "quality": ""}
                    entry = {"name": nm, "acquire": acq, "img": im.get("path", ""),
                             "asset": im.get("name", ""), "quality": im.get("quality", ""),
                             "code": _skin_code(im.get("name", ""), num),
                             "ecode": _emoji_code(im.get("name", ""), num)}
                    if cur_sec in cosmetics:
                        cosmetics[cur_sec].append(entry)
    # 表情行同时进 emojis 候选
    for e in cosmetics["表情"]:
        e["kind"] = "emoji"
    # 皮肤行 -> 对齐到皮肤
    for e in cosmetics["皮肤"]:
        for sk in skins:
            if sk["code"] and e["code"] and sk["code"] == e["code"]:
                sk["acquire"] = e["acquire"]
                if not sk.get("quality"):
                    sk["quality"] = ""
                sk["shop_quality"] = e["quality"]
                break
    for e in cosmetics["角色"]:
        for sk in skins:
            if sk["kind"] == "default" and e["acquire"]:
                sk["acquire"] = e["acquire"]

    # ---- 表情 ----
    emo = []
    seen_code = set()
    for it in emojis:
        code = _emoji_code(it["name"], num)
        emo.append({"code": code, "img": it["path"], "asset": it["name"],
                    "name": "", "quality": "", "acquire": "", "jp": "JP" in it["name"]})
        seen_code.add(code)
    # 用获取表补名称/品质/获取
    for row in cosmetics["表情"]:
        hit = None
        for e in emo:
            if row["ecode"] and e["code"] == row["ecode"] and not e["jp"]:
                hit = e
                break
        if hit is None:
            if row["ecode"] and row["ecode"] not in seen_code:
                emo.append({"code": row["ecode"], "img": row["img"], "asset": row["asset"],
                            "name": row["name"], "quality": row["quality"],
                            "acquire": row["acquire"], "jp": False})
                seen_code.add(row["ecode"])
            continue
        hit["name"] = row["name"]
        hit["quality"] = row["quality"]
        hit["acquire"] = row["acquire"]
    # 没名称的兜底
    for e in emo:
        if not e["name"]:
            n = e["code"].lstrip("0") or e["code"]
            e["name"] = f"表情{n}" + ("（日服）" if e["jp"] else "")
    emo.sort(key=lambda x: (x["jp"], x["code"]))

    # 封面：默认皮肤立绘
    portrait = head = ""
    for sk in skins:
        if sk["kind"] == "default":
            portrait = sk["imgs"].get("art", {}).get("path", "")
            head = sk["imgs"].get("head", {}).get("path", "")
    if not portrait:
        for sk in skins:
            portrait = portrait or sk["imgs"].get("art", {}).get("path", "")
    if not head:
        for sk in skins:
            head = head or sk["imgs"].get("head", {}).get("path", "")

    # 其它杂图（起始点 / 名片奖励 / 头像鼠 …）
    other_list = []
    for it in others:
        if img_types.classify(it["name"], it.get("cap")) == img_types.ICON:
            continue
        other_list.append({"cap": it.get("cap") or it["name"], "path": it["path"],
                           "name": it["name"], "kind": it["kind"]})

    bio = [f.get(f"人物传记{i}", "") for i in range(1, 6)]
    bio = [b for b in bio if b]
    pve = [f.get(f"PVE{i}", "") for i in range(1, 6)]
    pve = [p for p in pve if p]
    gifts = [f.get(f"礼物{i}", "") for i in range(1, 6)]
    gifts = [g for g in gifts if g]

    return {
        "name": name,
        "page_id": (char_rec or {}).get("pageid"),
        "gallery_id": (gallery_rec or {}).get("pageid"),
        "obtain_id": (obtain_rec or {}).get("pageid"),
        "number": num,
        "title": f.get("称号", ""),
        "en": f.get("英文名", ""),
        "jp": f.get("日文名", ""),
        "full_name": f.get("姓名", ""),
        "period": f.get("时期", ""),
        "gender": f.get("性别", ""),
        "org": f.get("从属组织", ""),
        "birthday": f.get("生日", ""),
        "food": f.get("喜欢的食物", ""),
        "event": f.get("事件经历", ""),
        "released": f.get("上线时间", ""),
        "stats": stats,
        "skills": skills,
        "potential": f.get("potential", ""),
        "skill_note": f.get("技能效果", ""),
        "bio": bio,
        "pve": pve,
        "gifts": gifts,
        "badges": [f.get(f"徽章{i}", "") for i in (1, 2) if f.get(f"徽章{i}")],
        "dice": f.get("骰子", ""),
        "tpl": tpl,
        "skins": skins,
        "emojis": emo,
        "cosmetics": cosmetics,
        "others": other_list,
        "voices": parse_voice((char_rec or {}).get("html", "")),
        "portrait": portrait,
        "head": head,
    }
