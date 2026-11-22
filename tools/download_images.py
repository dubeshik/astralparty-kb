#!/usr/bin/env python3
"""把 wiki 页面引用的图片下载到本地并压缩为 WebP（GIF 保留原格式）。

用法: python tools/download_images.py [--workers 6] [--limit N]
进度与映射写入 data/images/manifest.json，支持断点续传。
"""
import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "_vendor"))
from PIL import Image  # noqa: E402

DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
IMAGES = os.path.join(DATA, "images")
MANIFEST = os.path.join(IMAGES, "manifest.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
REFERER = "https://wiki.biligame.com/"


def norm_url(u):
    u = (u or "").strip()
    if u.startswith("//"):
        u = "https:" + u
    if not u.startswith("http"):
        return ""
    return u.split("?")[0]


def collect():
    info = {}
    with open(os.path.join(RAW, "pages.jsonl"), encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            for m in re.finditer(r"<img\b[^>]*>", d.get("html", "")):
                tag = m.group(0)
                s = re.search(r'src=["\']([^"\']+)', tag)
                u = norm_url(s.group(1) if s else "")
                if not u:
                    continue
                a = re.search(r'alt=["\']([^"\']*)', tag)
                alt = (a.group(1) if a else "").strip()
                rec = info.setdefault(u, {"alt": "", "pages": []})
                if alt and (not rec["alt"] or len(alt) < len(rec["alt"])):
                    rec["alt"] = alt
                if d["pageid"] not in rec["pages"]:
                    rec["pages"].append(d["pageid"])
    return info


def fname(url):
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    if url.lower().split("?")[0].endswith(".gif"):
        return h + ".gif"
    return h + ".webp"


def fetch(url, timeout=35):
    cmd = ["curl", "-s", "-m", str(timeout), "-A", UA, "-H", "Referer: " + REFERER,
           "--retry", "3", "--retry-delay", "1", "--retry-all-errors", url]
    for attempt in range(3):
        p = subprocess.run(cmd, capture_output=True)
        if p.returncode == 0 and len(p.stdout) > 100:
            return p.stdout
        time.sleep(1 + attempt)
    return None


def process(url, rec):
    name = fname(url)
    path = os.path.join(IMAGES, name)
    if os.path.exists(path) and os.path.getsize(path) > 100:
        rec["file"] = name
        rec["status"] = "cached"
        try:
            with Image.open(path) as im:
                rec["w"], rec["h"] = im.size
        except Exception:
            pass
        return url, rec
    raw = fetch(url)
    if raw is None:
        rec["status"] = "failed"
        return url, rec
    try:
        if name.endswith(".gif"):
            with open(path, "wb") as f:
                f.write(raw)
            size = len(raw)
            with Image.open(io.BytesIO(raw)) as im:
                rec["w"], rec["h"] = im.size
        else:
            with Image.open(io.BytesIO(raw)) as im:
                rec["w"], rec["h"] = im.size
                im.thumbnail((720, 720), Image.LANCZOS)
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGBA" if "A" in im.getbands() or im.mode == "P" else "RGB")
                im.save(path, "WEBP", quality=82, method=4)
            size = os.path.getsize(path)
        rec.update({"file": name, "status": "ok", "bytes": size,
                    "orig_bytes": len(raw)})
    except Exception as exc:
        rec["status"] = "failed:" + str(exc)[:80]
    return url, rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    os.makedirs(IMAGES, exist_ok=True)
    manifest = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            manifest = json.load(f)
    info = collect()
    todo = {u: r for u, r in info.items() if u not in manifest or manifest[u].get("status") == "failed"}
    if args.limit:
        todo = dict(list(todo.items())[:args.limit])
    print(f"共 {len(info)} 张图片，已有 {len(manifest)} 条记录，本次待处理 {len(todo)} 张", flush=True)

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(process, u, dict(r)) for u, r in todo.items()]
        for fut in concurrent.futures.as_completed(futures):
            u, rec = fut.result()
            manifest[u] = rec
            done += 1
            if done % 100 == 0:
                with open(MANIFEST, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=1)
                ok = sum(1 for x in manifest.values() if x.get("file"))
                print(f"[{done}/{len(todo)}] 成功 {ok} | {rec.get('status')}", flush=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    files = [x for x in os.listdir(IMAGES) if x.endswith((".webp", ".gif"))]
    total = sum(os.path.getsize(os.path.join(IMAGES, x)) for x in files)
    print(f"完成：{len(files)} 个本地图片文件，共 {total/1024/1024:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
