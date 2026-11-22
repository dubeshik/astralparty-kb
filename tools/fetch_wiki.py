#!/usr/bin/env python3
"""抓取 wiki.biligame.com/starengine 全部主命名空间页面，保存为原始 JSONL。

支持断点续传：已抓取的 pageid 会跳过。
用法: python tools/fetch_wiki.py [--delay 0.15] [--limit N]
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
COOKIE = os.path.join(RAW, "cookies.txt")
OUT = os.path.join(RAW, "pages.jsonl")
BASE = "https://wiki.biligame.com/starengine/api.php"
REFERER = "https://wiki.biligame.com/starengine/%E9%A6%96%E9%A1%B5"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 知识库只要游戏内容：排除站务/模板/沙盒/测试/旧版/同人/赛事/语音等无关页面
EXCLUDE_EXACT = {
    "-", "Lua", "MediaWiki", "Widget", "DIY工具", "模块", "模板", "分类",
    "创建新页面", "文件", "用户", "公告", "PsychologicalTest", "神秘页面",
    "加载提示", "暂无", "其他", "其余", "书签", "文章预设", "视频文章预设",
    "添加模板", "吉星派对Wiki", "首页", "首页的公告", "抽卡模拟器",
    "星趴卡牌合成器", "星趴筹码制成器", "星趴角色生成器", "往届优秀DIY作品",
    "测试筹码", "排行榜", "角色模型", "梦想号模型", "删号风波",
    "Steam「星引擎 Party」游戏日志", "《星引擎》游戏日志",
    "《星引擎party》已经登陆了steam页面并开启了愿望单",
    "重生！星引擎Star Engine！", "【星引擎】企划看板oc——恋 Koi",
    "恋的壁纸，想要的同学可以自取哦~不过请不要用在奇怪的地方",
    "「アストラルパーティー」ゲーム内お知らせ",
    "首届启航杯（5.29-6.2）——星引擎系列赛事",
    "星引擎Party赛事系列首届命运杯（5.2-5.5）", "游戏卫星合集", "星趴首次测试！",
}
EXCLUDE_PREFIX = ("沙盒", "旧-", "首页活动/", "用户:")
EXCLUDE_SUFFIX = ("/语音",)


def is_relevant(title):
    return not (title in EXCLUDE_EXACT
                or title.startswith(EXCLUDE_PREFIX)
                or title.endswith(EXCLUDE_SUFFIX))


def curl(url, timeout=60, tries=5):
    """用 curl 发请求（站点的 WAF 对 python urllib 不友好）。"""
    for attempt in range(tries):
        cmd = ["curl", "-s", "-m", str(timeout), "-b", COOKIE, "-c", COOKIE,
               "-A", UA, "-H", "Referer: " + REFERER, url]
        p = subprocess.run(cmd, capture_output=True)
        raw = p.stdout
        try:
            obj = json.loads(raw.decode("utf-8"))
            if "error" in obj:
                raise RuntimeError(obj["error"].get("info", "api error"))
            return obj
        except Exception as exc:
            if attempt == tries - 1:
                raise RuntimeError(f"request failed after {tries} tries: {url[:120]} -> {exc}")
            time.sleep(2.0 * (attempt + 1) + random.random())


def api(params, **kw):
    params = dict(params)
    params["format"] = "json"
    return curl(BASE + "?" + urllib.parse.urlencode(params), **kw)


def list_pages():
    pages, cont = [], {}
    while True:
        p = {"action": "query", "list": "allpages", "aplimit": "500", "apnamespace": "0"}
        p.update(cont)
        d = api(p)
        pages.extend(d.get("query", {}).get("allpages", []))
        if "continue" not in d:
            return pages
        cont = d["continue"]
        time.sleep(0.2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.15)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    os.makedirs(RAW, exist_ok=True)
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["pageid"])
                except Exception:
                    pass

    all_pages = list_pages()
    excluded = [p["title"] for p in all_pages if not is_relevant(p["title"])]
    pages = [p for p in all_pages if is_relevant(p["title"])]
    print(f"站点主命名空间 {len(all_pages)} 页，排除无关 {len(excluded)} 页，"
          f"保留游戏内容 {len(pages)} 页，已抓取 {len(done)} 页", flush=True)
    with open(os.path.join(RAW, "excluded.json"), "w", encoding="utf-8") as f:
        json.dump(excluded, f, ensure_ascii=False, indent=2)
    if args.limit:
        pages = pages[:args.limit]

    # 预热：先访问首页拿 cookie
    subprocess.run(["curl", "-s", "-m", "30", "-c", COOKIE, "-b", COOKIE,
                    "-A", UA, REFERER, "-o", os.devnull], capture_output=True)

    new = 0
    with open(OUT, "a", encoding="utf-8") as fout:
        for i, item in enumerate(pages, 1):
            pid, title = item["pageid"], item["title"]
            if pid in done:
                continue
            try:
                d = api({"action": "parse", "pageid": pid, "prop": "text|wikitext|categories|links",
                         "formatversion": "2"})
                parsed = d["parse"]
                rec = {
                    "pageid": pid,
                    "title": title,
                    "html": parsed.get("text", ""),
                    "wikitext": parsed.get("wikitext", ""),
                    "categories": [c["category"] for c in parsed.get("categories", [])],
                    "links": [l["title"] for l in parsed.get("links", [])],
                    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fout.flush()
                new += 1
                if i % 25 == 0 or new % 25 == 0:
                    print(f"[{i}/{len(pages)}] 新增 {new} | {title}", flush=True)
            except Exception as exc:
                print(f"[{i}/{len(pages)}] 失败 {title}: {exc}", flush=True)
            time.sleep(args.delay + random.random() * 0.08)
    print(f"完成，本次新增 {new} 页 -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
