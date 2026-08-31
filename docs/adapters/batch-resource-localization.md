# 批量资源扫描与人工翻译

批量工作流用于查找分散在整个 CryEngine 游戏目录中的文本资源。它不调用机器翻译：先导出 CSV，由人工填写译文，再生成独立 overlay PAK。

## 输出与安全边界

- 扫描会遍历游戏根目录内的 ZIP 风格 PAK 和松散候选文件，但不会解包整包或写游戏文件。
- `Localization/` 路径下可正常解析的 JSON 与 SpreadsheetML XML 是可写入资源；构建时只把有译文的成员写入新 PAK。
- GFX/CFX/SWF、普通/损坏 JSON、普通 XML 和文本文件中的可读字符串会写入按类型分片的 `report-only` CSV，状态为 `report-only`。这些条目仅用于查漏，构建不会回写它们，即使填写了 `translation`。
- CSV 的 `source_archive`、`resource_id`、`source_path`、`text_key`、`original_text`、`original_hash` 和 `status` 都是只读字段。只填写 `translation`。
- 生成 PAK 的内部成员路径始终保留游戏原始路径和文件名；输出 PAK 必须在游戏目录外。

## 配置与 CLI

在项目 profile 的 `batch` 对象中设置：

```json
{
  "batch": {
    "enabled": true,
    "game_root": "D:/Games/Example",
    "catalog_csv": "work/all-text.csv",
    "legacy_translation_csv": "work/previous-translations.csv",
    "scan_report": "work/scan-report.json",
    "translation_overlay_pak": "work/zzz_translation.pak",
    "manifest": "work/manifest.json",
    "font_file": "",
    "font_overlay_pak": "",
    "ffdec": ""
  }
}
```

依次运行：

```powershell
cry-localize workflow batch-scan project.json
# 可选：只预览旧表能复用的译文数
cry-localize workflow batch-reuse-old project.json --dry-run
# 备份当前 active CSV 后写入可安全复用的旧译文
cry-localize workflow batch-reuse-old project.json
# 手工编辑 work\all-text.csv 的 translation 列
cry-localize workflow batch-dry-run project.json
cry-localize workflow batch-build project.json
```

`batch-scan` 的 `catalog_csv` 只保存 `active` 翻译行，适合直接在 Excel/WPS 打开。`scan_report` 同目录会生成 `<报告名>-parts/report-index.csv`，以及按 `json`、`xml`、`gfx`、`other` 分类、每份最多 10,000 行的 `report-only` 分片。`batch-scan` 已存在这些输出时拒绝覆盖，除非传入 `--overwrite`。`batch-dry-run` 只显示可写入译文；`report-only` 项不会显示为计划变更。`batch-build` 创建翻译 PAK 和 Manifest，但不会自动安装到游戏目录。

当 profile 的 `overlay_mode` 为 `english-path-overlay`（War of Rights 的推荐设置）时，只有 `Localization/english/` 下的可写资源保持 `active`；其它语言目录自动降为 `report-only`，避免翻译不会被该加载方式采用的文本。

## 复用已有人工译文

在 `legacy_translation_csv` 填已有翻译表，或在 CLI 使用 `--old-csv <CSV>` 覆盖该路径。复用规则按以下顺序执行：

1. 先把新 CSV 的来源 PAK 前缀移除后，精确匹配旧 CSV 的 `resource_id`，可保留重复 key 的 `#1`/`#2` 顺序。
2. 无精确 ID 时，只在 `source_path`、`text_key` 和 `original_hash` 三项完全相同时复用。
3. 新 CSV 已有译文绝不覆盖；有多个旧候选的条目不猜测、不写入，而是列在报告的 `ambiguous_hash_matches` 中。

先运行 `batch-reuse-old --dry-run` 查看数量。实际执行会生成 `translations-active.before-reuse.csv`（如已存在则自动递增编号）和 `translations-active.reuse-report.json`，然后才写入 active CSV。

## 全量字体替换（可选）

同时填写 `font_file`、`font_overlay_pak` 和可用的 `ffdec` 路径后，`batch-build` 会扫描每个发现的 `.gfx`/`.cfx`，把所有检测到的 `DefineFont3` 槽位替换为同一字体。输出 PAK 仍保留每个原始 GFX 的内部路径和文件名。

任一已发现 GFX 的槽位扫描或替换失败时，字体 PAK 不会生成。FFDec 不随本项目分发；先用 `cry-localize tools doctor --ffdec <FFDEC_CLI>` 验证路径。字体 PAK 生成后仍应在游戏中人工验证，再通过现有 Install 页面/命令执行带备份的安装。
