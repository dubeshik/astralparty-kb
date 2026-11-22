#!/usr/bin/env python3
"""本地知识库检索：给 AI 或命令行使用，无第三方依赖。

示例:
  python tools/kb_search.py "芬妮 皮肤"            # 片段检索（多关键词 AND）
  python tools/kb_search.py "清凉盛夏" --full      # 整页 Markdown
  python tools/kb_search.py "筹码" --category 筹码 --limit 3
  python tools/kb_search.py --list-categories
  python tools/kb_search.py --characters           # 列出所有角色与皮肤数
  python tools/kb_search.py --characters 芬妮      # 单个角色的结构化档案
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
INDEX = os.path.join(DATA, "index.json")
CHUNKS = os.path.join(DATA, "chunks.jsonl")
CHARS = os.path.join(DATA, "characters.json")
CATS = os.path.join(DATA, "categories.json")


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_chunks():
    if not os.path.exists(CHUNKS):
        return []
    with open(CHUNKS, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def search(terms, category=None, limit=5, kind=None):
    scored = []
    for c in load_chunks():
        if category and category.lower() not in c["category"].lower():
            continue
        if kind and c.get("kind") != kind:
            continue
        text = c["text"].lower()
        title = c["title"].lower()
        if not all(k in text or k in title for k in terms):
            continue
        score = 0
        for k in terms:
            if k == title:
                score += 40
            elif k in title:
                score += 14
            if c.get("section") and k in c["section"].lower():
                score += 6
            score += min(text.count(k), 10)
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return scored[:limit]


def find_page(query, category=None):
    pages = (load_json(INDEX, {}) or {}).get("pages", [])
    terms = [q.lower() for q in query.split()]
    best, best_score = None, 0
    for p in pages:
        if category and category.lower() not in p["category"].lower():
            continue
        title = p["title"].lower()
        score = 0
        for k in terms:
            if k == title:
                score += 50
            elif k in title:
                score += 20
        if score > best_score:
            best, best_score = p, score
    return best


def read_page(page):
    path = os.path.join(DATA, "markdown", page["file"])
    if not os.path.exists(path):
        return "[找不到页面文件]"
    with open(path, encoding="utf-8") as f:
        return f.read()


def cmd_categories():
    d = load_json(CATS, {}) or {}
    groups = d.get("groups") or []
    if groups:
        for g in groups:
            names = "、".join(f'{c["name"]}({c["count"]})' for c in g["cats"])
            print(f'{g["name"]:8} {names}')
    else:
        for c in d.get("all") or []:
            print(f'{c["count"]:4d}  {c["name"]}')


def cmd_characters(name=None):
    chars = load_json(CHARS, []) or []
    if not name:
        print(f"共 {len(chars)} 位角色\n")
        print(f'{"角色":12} {"编号":6} {"皮肤":4} {"表情":4}  皮肤列表')
        for c in sorted(chars, key=lambda x: x["name"]):
            skins = "、".join(s["name"] for s in c["skins"])
            print(f'{c["name"]:12} {c["number"] or "-":6} {len(c["skins"]):<4} '
                  f'{len(c["emojis"]):<4}  {skins}')
        return
    hit = next((c for c in chars if name in c["name"]), None)
    if not hit:
        print(f"没有找到角色：{name}")
        return
    c = dict(hit)
    c["cosmetics"] = {k: v for k, v in c.get("cosmetics", {}).items() if v}
    print(json.dumps(c, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description="吉星派对本地知识库检索")
    ap.add_argument("query", nargs="*", help="关键词，空格分隔（需全部命中）")
    ap.add_argument("--limit", type=int, default=5, help="返回片段数，默认 5")
    ap.add_argument("--category", help="按分类过滤，如 角色 / 筹码 / 卡牌/手牌")
    ap.add_argument("--kind", help="按类型过滤：char / relic / card / monster / event …")
    ap.add_argument("--json", action="store_true", help="输出 JSON（供程序调用）")
    ap.add_argument("--full", action="store_true", help="输出匹配页面的完整 Markdown")
    ap.add_argument("--list-categories", action="store_true", help="列出分类")
    ap.add_argument("--characters", nargs="?", const="", metavar="角色名",
                    help="列出角色与皮肤；给名字则输出该角色结构化数据")
    args = ap.parse_args()

    if not os.path.exists(INDEX):
        print("知识库未构建：请先运行 python tools/build_kb.py", file=sys.stderr)
        sys.exit(1)

    if args.list_categories:
        cmd_categories()
        return
    if args.characters is not None:
        cmd_characters(args.characters or None)
        return

    query = " ".join(args.query).strip()
    if not query:
        ap.print_help()
        return
    terms = [q.lower() for q in re.split(r"\s+", query) if q]

    if args.full:
        page = find_page(query, args.category)
        if not page:
            print("没有匹配的页面")
            return
        text = read_page(page)
        if args.json:
            print(json.dumps({"title": page["title"], "category": page["category"],
                              "file": page["file"], "content": text},
                             ensure_ascii=False))
        else:
            print(text)
        return

    hits = search(terms, args.category, args.limit, args.kind)
    if args.json:
        print(json.dumps([{"score": s, **c} for s, c in hits],
                         ensure_ascii=False, indent=2))
        return
    if not hits:
        print("没有匹配内容。试试更短的关键词，或 --list-categories 看分类。")
        return
    for i, (score, c) in enumerate(hits, 1):
        head = f'{i}. {c["title"]}' + (f' › {c["section"]}' if c.get("section") else "")
        print(f"=== {head}  [{c['category']} | {c['page_id']} | {score}] ===")
        print(c["text"])
        print()


if __name__ == "__main__":
    main()
