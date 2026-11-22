#!/usr/bin/env python3
"""按模板语义重建「结构化正文」。

筹码 / 手牌 / 怪物 / 事件 这几类页面的 wiki 正文，是模板拼出来的卡片图 + 重复
文字，直接摊平会变成一坨跑马灯。这里改为用 wikitext 字段重建：

    怪物 -> 数值表（难度 × 攻/防/血）、主动/被动技能、机制、出没地图
    手牌 -> 效果（PVP/PVE）、附录、花絮、历史
    筹码 -> 效果、详解、历史
    事件 -> 各难度效果、出现地图

生成的块结构与 extract.py 完全一致，渲染层无需区分。
"""
import re


def _tok(text):
    text = (text or "").strip()
    if not text:
        return []
    # 保留换行 -> 段落切分由调用方处理
    return [("t", text)]


def _p(text):
    toks = _tok(text)
    return {"t": "p", "in": toks} if toks else None


def _pb(label, text):
    """加粗标签 + 正文，例如「主动技能」+ 描述。"""
    toks = []
    if label:
        toks.append(("b", label))
    if text:
        toks.append(("t", ("：" if label else "") + text))
    return {"t": "p", "in": toks} if toks else None


def _kv(pairs):
    items = [{"k": [("t", k)], "v": [("t", v)]} for k, v in pairs if v]
    return {"t": "dl", "items": items} if items else None


def _table(head, rows):
    return {"t": "table", "head": [[("t", h)] for h in head],
            "rows": [[[("t", c)] for c in r] for r in rows]}


def _sec(title, blocks, level=2):
    return {"level": level, "title": title, "blocks": [b for b in blocks if b]}


def _num_triplet(v):
    parts = [x.strip() for x in re.split(r"[,，/\s]+", v or "") if x.strip()]
    return parts


DIFFS = ("普通", "困难", "噩梦", "疯狂", "极限")


def monster(f, title):
    secs = []
    lead = f.get("怪物传记") or f.get("机制内容") or ""
    if lead:
        secs.append(_sec("简介", [_p(lead)]))

    rows = []
    for d in DIFFS:
        v = f.get(d, "")
        if not v or v in ("-", "—", "-,-,-"):
            continue
        n = _num_triplet(v)
        if len(n) >= 3:
            rows.append([d, n[0], n[1], n[2], f.get("星币", "")])
    if rows:
        secs.append(_sec("数值（攻击 / 防御 / 生命）",
                         [_table(["难度", "攻击", "防御", "生命", "星币"], rows)]))

    skills = []
    if f.get("主动技能"):
        cd = f.get("主动技能冷却", "")
        skills.append(_pb(f"主动技能｜{f['主动技能']}" + (f"（冷却 {cd}）" if cd else ""),
                          f.get("主动技能描述", "")))
    if f.get("被动技能"):
        skills.append(_pb(f"被动技能｜{f['被动技能']}", f.get("被动技能描述", "")))
    if f.get("技能效果"):
        skills.append(_pb("技能效果", f["技能效果"]))
    if skills:
        secs.append(_sec("技能", skills))

    if f.get("机制内容"):
        secs.append(_sec("机制", [_p(f["机制内容"]),
                                _kv([("机制标签", f.get("机制", ""))])]))

    return secs


def card(f, title):
    secs = []
    eff = []
    if f.get("内容(PVP)") or f.get("内容"):
        pvp = f.get("内容(PVP)") or f.get("内容")
        eff.append(_pb("标准对战（PVP）", pvp))
    if f.get("内容(PVE)"):
        eff.append(_pb("合作挑战（PVE）", f["内容(PVE)"]))
    if eff:
        secs.append(_sec("卡牌效果", eff))

    meta = _kv([("编号", f.get("编号", "")), ("类型", f.get("类型", "")),
                ("对象", f.get("对象", "")), ("英文名", f.get("英文", "")),
                ("来源", f.get("来源", "")),
                ("附录", " / ".join(x for x in (f.get("附录1", ""), f.get("附录2", "")) if x))])
    if meta:
        secs.append(_sec("资料", [meta]))

    if f.get("详解"):
        secs.append(_sec("详解", [_p(f["详解"])]))
    if f.get("花絮"):
        secs.append(_sec("花絮", [_p(f["花絮"])]))
    if f.get("历史"):
        secs.append(_sec("历史", [_p(f["历史"])]))
    return secs


def relic(f, title):
    secs = []
    if f.get("描述"):
        secs.append(_sec("效果", [_p(f["描述"])]))
    meta = _kv([("品质", f.get("品质", "")), ("编号", f.get("编号", "")),
                ("类别", f.get("类别", ""))])
    if meta:
        secs.append(_sec("资料", [meta]))
    if f.get("详解"):
        secs.append(_sec("详解", [_p(f["详解"])]))
    if f.get("历史"):
        secs.append(_sec("历史", [_p(f["历史"])]))
    return secs


def event(f, title):
    secs = []
    blocks = []
    d1, d2 = f.get("难度1", ""), f.get("难度2", "")
    if f.get("内容"):
        blocks.append(_pb(d1 or "内容", f["内容"]))
    if f.get("内容2"):
        blocks.append(_pb(d2 or "内容2", f["内容2"]))
    if blocks:
        secs.append(_sec("效果", blocks))
    return secs


BUILDERS = {"monster": monster, "card": card, "relic": relic, "event": event}


def build(kind, fields, title):
    fn = BUILDERS.get(kind)
    if not fn:
        return []
    try:
        return fn(fields, title)
    except Exception:
        return []
