#!/usr/bin/env python3
"""识别素材类型：根据 wiki 原始文件名（权威）与画廊标题（人工标签）。

原始文件名规律（game: 星引擎 Party）：
  UT_Item_Hero_102            头像（游戏内方形头像）
  UT_Hero_ProfilePhoto_102    Q版头像
  UT_Hero_Card_102            立绘（全身）
  UT_Hero_LevelUp_102         Q版立绘
  UT_Hero_Bust_102_0/1        主界面半身像（星币<20 / ≥20）
  UT_Item_StandingPainting_102 立绘缩略（头像栏用）
  UT_Item_Emoji_102_01        表情
  UT_AccountBackground_71102  名片（长条）
  UT_Item_AccountBackground_* 名片缩略
  UT_AccountHeadShot_70102    头像鼠（玩家头像）
  UT_Hero_RolePhoto_102       像素头像
  UT_Item_KV_76102            主页背景
  UT_Platform_102             起始点
  UT_HandCard / UT_MapEvent / UT_Monster_Card / UT_Event_Card  卡面实物
  UT_Relic_50042              筹码实物
  UT_Buff_* / UT_Currency_* / 稀有度_* / CardFront / Card0*   图标/卡框
"""
import re

# key -> (展示名, 说明, 排序权重)
KINDS = {
    "art":       ("立绘", "全身立绘", 100),
    "art_sfw":   ("立绘（和谐版）", "和谐版立绘", 96),
    "chibi":     ("Q版立绘", "Q版小人", 92),
    "head":      ("头像", "游戏内头像", 88),
    "headq":     ("Q版头像", "Q版头像", 86),
    "bust":      ("半身像", "主界面半身像", 70),
    "emoji":     ("表情", "聊天表情", 64),
    "nameplate": ("名片", "名片背景", 58),
    "item":      ("实物图", "卡面 / 道具 / 筹码", 54),
    "kv":        ("宣传图", "KV / 主页背景", 50),
    "platform":  ("起始点", "棋盘起始点", 44),
    "rolephoto": ("像素头像", "像素小人", 40),
    "headshot":  ("头像鼠", "玩家头像", 36),
    "reward":    ("羁绊奖励", "羁绊等级奖励图", 34),
    "gift":      ("礼物", "偏好礼物", 28),
    "material":  ("材料", "养成材料", 24),
    "dice":      ("骰子", "角色骰子", 20),
    "other":     ("其他图片", "", 10),
}
ICON = "icon"      # 纯图标/卡框/稀有度底图，不进画廊

# 画廊标题 -> 皮肤槽位。必须先精确匹配，否则「Q版头像」会被「头像」抢走。
SLOT_EXACT = {
    "头像": "head",
    "q版头像": "headq",
    "立绘": "art",
    "q版立绘": "chibi",
    "立绘（和谐版）": "art_sfw",
    "立绘(和谐版)": "art_sfw",
    "当星币数＜20时": "bust_low",
    "当星币数<20时": "bust_low",
    "当星币数≥20时": "bust_high",
    "当星币数>=20时": "bust_high",
    "起始点": "platform",
    "像素头像": "rolephoto",
    "头像鼠": "headshot",
}
SLOT_LABEL = {
    "art": "立绘", "art_sfw": "和谐版立绘", "chibi": "Q版立绘", "head": "头像",
    "headq": "Q版头像", "bust_low": "半身像（星币<20）", "bust_high": "半身像（星币≥20）",
    "nameplate": "名片", "platform": "起始点", "rolephoto": "像素头像",
    "headshot": "头像鼠", "reward": "羁绊奖励", "kv": "主页背景", "item": "实物图",
    "dice": "骰子", "gift": "礼物", "material": "材料", "other": "其他",
}

_ICON_KEYS = (
    "relicbase", "cardfront", "card0 ", "card00", "card1 ", "rarity", "稀有度",
    "buff", "currency", "icon", "skinquality", "starlight", "actnum",
    "matchentrance", "unnamed", "upgrade", "prophecy", "天赋", "升级",
)


def _low(name, caption):
    s = (name or "") + " " + (caption or "")
    return s.lower().replace("_", " ").replace("-", " ")


def classify(name, caption=""):
    """返回 KINDS 的 key；图标类返回 ICON。"""
    base = (name or "").lower()
    # 卡框、卡面装饰：Card0_Effect / CardFront / Card_Star 之类
    if re.match(r"^card\s*\d", base) or base.startswith(("card_star", "card star")):
        return ICON
    low = _low(name, caption)
    if any(k in low for k in _ICON_KEYS):
        return ICON
    cap = (caption or "").strip()
    # 画廊标题最可靠
    if cap:
        if "和谐" in cap:
            return "art_sfw"
        if cap == "立绘":
            return "art"
        if cap in ("q版立绘", "Q版立绘".lower()):
            return "chibi"
        if cap in ("头像",):
            return "head"
        if "q版头像" in cap.lower():
            return "headq"
        if "星币" in cap and "20" in cap:
            return "bust"
        if "起始点" in cap:
            return "platform"
        if "像素" in cap:
            return "rolephoto"
        if "头像鼠" in cap:
            return "headshot"
        if "名片" in cap:
            return "nameplate"
        if "奖励" in cap:
            return "reward"

    if "hero card" in low:
        return "art"
    if "hero levelup" in low:
        return "chibi"
    if "hero profilephoto" in low:
        return "headq"
    if "hero bust" in low:
        return "bust"
    if "hero rolephoto" in low:
        return "rolephoto"
    if "playerphoto" in low:
        return "head"
    if "cardback" in low or "item card" in low:
        return "item"
    if "item hero" in low or "standingpainting" in low:
        return "head"
    if "item emoji" in low:
        return "emoji"
    if "accountbackground" in low:
        return "nameplate"
    if "accountheadshot" in low:
        return "headshot"
    if "item kv" in low or "background" in low:
        return "kv"
    if "platform" in low:
        return "platform"
    if any(k in low for k in ("handcard", "mapevent", "monster card",
                              "event card", "relic ", "card art", "itemcard",
                              "item skill", "prop ", "item prop")):
        return "item"
    if "gift" in low or "礼物" in low:
        return "gift"
    if "material" in low or "材料" in low:
        return "material"
    if "dice" in low or "骰子" in low:
        return "dice"
    return "other"


def slot_of(caption):
    """皮肤分组内的图片标题 -> 槽位 key。"""
    c = (caption or "").strip()
    if not c:
        return ""
    low = c.lower()
    if low in SLOT_EXACT:
        return SLOT_EXACT[low]
    if "和谐" in c:
        return "art_sfw"
    if "星币" in c and "20" in c:
        return "bust_low" if ("<" in c or "＜" in c) else "bust_high"
    if "q版头像" in low:
        return "headq"
    if "q版立绘" in low:
        return "chibi"
    if low == "头像":
        return "head"
    if "起始点" in c:
        return "platform"
    if "像素" in c:
        return "rolephoto"
    if "头像鼠" in c:
        return "headshot"
    if "名片" in c:
        return "nameplate"
    if "奖励" in c:
        return "reward"
    return ""
