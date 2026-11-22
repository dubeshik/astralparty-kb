# 吉星派对知识库（给 AI 的使用说明）

从官方 BWIKI（https://wiki.biligame.com/starengine/首页 ）抓取并清洗的**离线游戏知识库**，
只包含游戏内容：角色、卡牌/手牌、筹码、事件、怪物、地图、活动、通行证、装扮、成就、公告等。
已排除站务页、模板、沙盒、测试页、旧版废弃页、同人创作、赛事外围与语音子页。

## 使用方法

本仓库地址可以尝试直接作为url导入服务器知识库中，若失败，我也没法（），因为我也在到处测试怎么完整加入，

将本仓库作为zip下载，可以直接通过路径/viewer/index.html直接访问全部词条page以及markdown，需要本地存储，服务器相关待更新。

## 数据规模（2026-11 构建）

| 项目 | 数量 |
| --- | --- |
| 词条 | 516 页（已把「/画廊」「/获取」等 56 个子页合并进角色页） |
| 角色 | 36 位，138 套皮肤、450 个表情 |
| RAG 分块 | 约 2290 块（按 `##` / `###` 章节切分，带章节路径） |

## 检索方式（按优先级）

1. **关键词检索（推荐）**
   ```
   python tools/kb_search.py "芬妮 皮肤" --limit 5
   ```
   - 多个关键词是 AND 关系，返回相关度最高的片段，可直接作为回答依据。
   - `--json` 结构化输出；`--category 角色` 按分类过滤；`--kind char|relic|card|monster|event` 按类型过滤。
   - `--list-categories` 查看分类与分组。

2. **读整页 Markdown**
   ```
   python tools/kb_search.py "清凉盛夏" --full
   ```
   或直接读 `data/markdown/p<pageid>.md`。文件顶部是分类/来源，正文保留了本地图片引用。

3. **角色结构化数据**
   ```
   python tools/kb_search.py --characters          # 列出角色、皮肤数、表情数
   python tools/kb_search.py --characters 芬妮     # 单个角色完整 JSON
   ```
   也可直接读 `data/characters.json`：每套皮肤含编号、品质、获取方式、
   立绘 / Q版立绘 / 头像 / Q版头像 / 半身像（星币<20、≥20）的本地图片路径；
   表情含名称、品质、获取方式；头像/名片/卡牌/骰子/主页背景清单同在其中。

## 数据目录

- `data/markdown/`：AI 友好 Markdown，一页一文件；`![说明](../images/xxx.webp)` 是本地图片引用，
  多模态模型可直接打开查看皮肤、卡面、地图示意。
- `data/chunks.jsonl`：`{id, page_id, title, category, kind, section, text}`，适合向量检索 / RAG 导入。
- `data/index.json`：全部词条的标题、分类、类型、摘要、字数、缩略图。
- `data/characters.json`：角色 / 皮肤 / 表情 / 装扮的结构化数据。
- `data/categories.json`：分类与侧边栏分组（角色、对局内容、外观与通行证、活动与版本、资料）。
- `data/images/`：本地图片，`manifest.json` 记录原始 URL → 文件；
  同一张图的多种缩略尺寸已按**原始文件名**归并，只保留分辨率最高的一份。
- `data/pages/`：可直接浏览的宽屏词条页（供 `viewer/` 使用）。
- `data/bundle.js`：查看器离线数据。
- `data/raw/pages.jsonl`：原始抓取数据（HTML + wikitext + 分类），重建时使用，一般无需直接读。

## 页面结构约定

- **角色页**是「一站式档案」：概览（数值/技能/潜能/基础资料/PVE 特性）、
  皮肤（默认 + 羁绊 + 全部皮肤，每套含 6 类图片与获取方式）、表情、
  装扮（头像/名片/卡牌/骰子/主页背景）、档案（传记/皮肤故事/画廊其他素材）、语音台词。
- 皮肤编号取自官方素材文件名：`102`（默认）、`102_Max`（羁绊）、`102_01…`（皮肤）；
  不要假设「皮肤只有 4 套」——官方模板只列 皮肤名1..N，羁绊皮肤另算。
- 筹码 / 手牌 / 怪物 / 事件 由模板字段重建为结构化正文（数值表、技能、机制、效果、历史），
  比原站渲染出来的「卡片文字 + 拼图」干净得多。
- 通行证页为「等级 × 免费 / 付费 / 付费+升级」三档奖励表。
- 角色页的皮肤分页：原版与和谐版立绘横向并排，右侧是品质、获取方式、头像/Q版/半身像缩略图与皮肤故事。
- 页面支持 `#tab-2`、`#tab-2.skin-3` 形式的锚点，可直接定位到某个分页/某套皮肤。

## 使用注意

- 回答时注明数据来自本知识库，并尽量附词条来源链接（`https://wiki.biligame.com/starengine/<词条名>`）。
- 数值、技能描述、版本号以知识库内文本为准；知识库没有的就说「本地知识库未收录」，不要编造。
- 数据有抓取时间点（`data/index.json` 的 `generated_at`），游戏可能已更新，时效性内容请提醒用户核对官方公告。
- 涉及外观、立绘、道具样貌的问题，请同时查看 Markdown 中引用的本地图片，不要只凭文字猜测。
- 有 8 位角色官方提供了 `/获取` 页（芬妮、小町、帕帕拉、帕露南、恋、派德曼、苍鲤、阿兰娜），
  这些角色的头像/名片/卡牌/骰子清单才完整；其余角色只有画廊里的零散素材。

## 更新流程

```
python tools/fetch_wiki.py       # 增量抓取页面（API，可断点续传）
python tools/download_images.py  # 下载新增图片（WebP 压缩，GIF 保留）
python tools/upgrade_images.py   # 把缩略图升级为原图
python tools/build_kb.py         # 重建全部产物
```

`build_kb.py` 会顺带删除已合并/下线页面的旧文件，并重新生成 index / chunks / characters / bundle。

## 代码结构

| 文件 | 职责 |
| --- | --- |
| `tools/fetch_wiki.py` | 抓 wiki API，写入 `data/raw/pages.jsonl` |
| `tools/download_images.py` | 下载图片 |
| `tools/upgrade_images.py` | 缩略图升级原图 |
| `tools/domutil.py` | 极简 DOM 解析 |
| `tools/img_index.py` | 图片按原始文件名归并去重 |
| `tools/img_types.py` | 素材类型识别（立绘/头像/Q版/表情/名片…） |
| `tools/extract.py` | HTML → 结构化块模型（段落/表格/画廊/列表/通行证…） |
| `tools/tpl_layout.py` | 筹码/手牌/怪物/事件的模板字段 → 结构化正文 |
| `tools/chargear.py` | 角色 × 皮肤 × 表情 × 装扮 数据合成 |
| `tools/render_page.py` | 块模型 → 宽屏词条页 HTML |
| `tools/render_md.py` | 块模型 → 面向 AI 的 Markdown |
| `tools/build_kb.py` | 编排构建 + 产出索引 |
| `tools/kb_search.py` | 命令行检索 |
| `tools/serve.py` | 本地静态服务器 |

人工浏览：双击 `start_kb.bat`（自动开浏览器），或直接打开 `viewer/index.html`。

wiki 页面结构若改版，通常只需调整 `extract.py`（选择器/噪声判定）与 `tpl_layout.py`（字段映射）。
