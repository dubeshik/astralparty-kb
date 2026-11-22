#!/usr/bin/env python3
"""把已下载的 100px 缩略图升级为原图（尤其角色立绘/头像）。

MediaWiki 缩略图 URL:
  .../images/<wiki>/thumb/a/ab/<hash>.png/100px-Name.png
原图 URL:
  .../images/<wiki>/a/ab/<hash>.png
"""
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_vendor"))
from PIL import Image  # noqa: E402

DATA = os.path.join(ROOT, "data")
IMAGES = os.path.join(DATA, "images")
MANIFEST = os.path.join(IMAGES, "manifest.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
REFERER = "https://wiki.biligame.com/"


def original_url(thumb_url):
    m = re.match(r"(https?://[^/]+/images/[^/]+)/thumb/([0-9a-f]/[0-9a-f]{2})/([^/]+)/\d+px-(.+)$", thumb_url)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return None


def fetch(url, timeout=45, tries=3):
    cmd = ["curl", "-s", "-m", str(timeout), "-A", UA, "-H", "Referer: " + REFERER,
           "--retry", "2", "--retry-all-errors", url]
    for i in range(tries):
        p = subprocess.run(cmd, capture_output=True)
        if p.returncode == 0 and len(p.stdout) > 100:
            return p.stdout
        time.sleep(1 + i)
    return None


def process(item):
    url, rec = item
    src = rec.get("file")
    if not src or not url:
        return url, rec, False
    orig = original_url(url)
    if not orig:
        return url, rec, False
    path = os.path.join(IMAGES, src)
    try:
        with Image.open(path) as im:
            if max(im.size) >= 500:
                return url, rec, False  # 已是大图
    except Exception:
        pass
    raw = fetch(orig)
    if not raw:
        return url, rec, False
    import io
    try:
        with Image.open(io.BytesIO(raw)) as im:
            ow, oh = im.size
            if ow <= 120 and oh <= 120:
                return url, rec, False
            im.thumbnail((900, 900), Image.LANCZOS)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            im.save(path, "WEBP", quality=85, method=4)
            rec["w"], rec["h"] = im.size
            rec["upgraded"] = True
            rec["bytes"] = os.path.getsize(path)
    except Exception:
        return url, rec, False
    return url, rec, True


def main():
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    candidates = [(u, v) for u, v in manifest.items()
                  if v.get("file") and original_url(u) and max(v.get("w", 0), v.get("h", 0)) <= 150]
    print(f"候选缩略图 {len(candidates)} 张，开始升级原图…", flush=True)
    upgraded = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(process, x) for x in candidates]
        for k, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            u, rec, ok = fut.result()
            manifest[u] = rec
            if ok:
                upgraded += 1
            if k % 100 == 0:
                print(f"[{k}/{len(candidates)}] 已升级 {upgraded}", flush=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"完成：升级 {upgraded} 张原图", flush=True)


if __name__ == "__main__":
    main()
