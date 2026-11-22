#!/usr/bin/env python3
"""图片索引：把 wiki 上同一张图的多种缩略尺寸归一到「原始文件名」。

MediaWiki 的图片地址通常是
  .../images/<wiki>/thumb/a/ab/<hash>.png/120px-Name.png
   .../images/<wiki>/thumb/a/ab/<hash>.png/80px-Name.png
   .../images/<wiki>/a/ab/<hash>.png              (原图)
三者的「逻辑图片」是同一张 Name.png。旧版按 URL 建索引，导致同一张图
被下载成多份、画廊里同一张立绘出现三四遍。这里统一按 Name.png 归并，
并优先选用像素面积最大的本地文件。
"""
import json
import os
import re
import urllib.parse

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
MANIFEST = os.path.join(DATA, "images", "manifest.json")

_THUMB_RE = re.compile(r"^\d+px-", re.I)


def norm_url(u):
    u = (u or "").strip()
    if u.startswith("//"):
        u = "https:" + u
    if not u.startswith("http"):
        return ""
    return u.split("?")[0]


def canonical(url):
    """URL -> 逻辑文件名（如 UT_Hero_Card_102_01.png）。"""
    u = norm_url(url)
    if not u:
        return ""
    name = urllib.parse.unquote(u.rsplit("/", 1)[-1])
    name = _THUMB_RE.sub("", name)
    # 去掉 wiki 常见的 "xxx.png.jpg" 之类怪后缀重复
    return name.strip()


class ImageIndex:
    def __init__(self, manifest_path=MANIFEST):
        self.by_name = {}       # canonical -> {"file","w","h","alt"}
        self.url_to_name = {}   # 原始 URL -> canonical
        self.files = set()
        if not os.path.exists(manifest_path):
            return
        with open(manifest_path, encoding="utf-8") as f:
            raw = json.load(f)
        for url, rec in raw.items():
            if not rec.get("file"):
                continue
            name = canonical(url)
            if not name:
                continue
            self.url_to_name[url] = name
            self.files.add(rec["file"])
            area = (rec.get("w") or 0) * (rec.get("h") or 0)
            cur = self.by_name.get(name)
            if cur is None or area > cur["area"]:
                self.by_name[name] = {
                    "file": rec["file"], "w": rec.get("w") or 0,
                    "h": rec.get("h") or 0, "area": area,
                    "alt": (rec.get("alt") or "").strip(),
                }

    def name_of(self, url):
        """任意图片 URL -> 逻辑文件名（即使本地没下载也能得到名字）。"""
        u = norm_url(url)
        return self.url_to_name.get(u) or canonical(u)

    def local(self, name):
        rec = self.by_name.get(name)
        return ("../images/" + rec["file"]) if rec else ""

    def resolve(self, url_or_name):
        """返回 (逻辑文件名, 本地相对路径)，本地缺失时路径为空串。"""
        name = self.name_of(url_or_name) if url_or_name.startswith(("http", "//")) \
            else url_or_name
        return name, self.local(name)

    def size(self, name):
        rec = self.by_name.get(name)
        return (rec["w"], rec["h"]) if rec else (0, 0)
