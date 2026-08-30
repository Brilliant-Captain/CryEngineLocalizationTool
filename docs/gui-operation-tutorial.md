# GUI 操作教程（通用 CryEngine 项目）

本教程按真实 CryEngine 项目的验证流程编写。文中的 `<GAME_ROOT>`、`<SOURCE_PAK>`、`<UI_PAK>`、`<WORK_ROOT>`、`<FFDEC_CLI>` 和 `<FONT_FILE>` 都是占位符，应替换为实际路径。源 PAK、字体和游戏目录应保留在仓库之外。

## 0. 准备

准备一个 CryEngine 源 PAK；处理字体时还需要 FFDec 命令行程序 `ffdec-cli.exe` 和一个 TTF/OTF 字体。发布 EXE 已内置 fontTools，覆盖率检查和子集生成默认不需要额外 Python；仅在使用自定义 Python 环境时填写 GUI 中的“fontTools 自定义 Python（可选）”。

## 1. 翻译流程

### 1.1 创建项目配置

启动 CryEngineLocalization.exe，在“项目”页填写项目名称、源 PAK、翻译 CSV、输出翻译 PAK、Manifest、目标语言和覆盖模式。示例：

~~~text
源 PAK：<SOURCE_PAK>
翻译 CSV：<WORK_ROOT>\translations.csv
翻译输出 PAK：<WORK_ROOT>\translation_overlay.pak
Manifest：<WORK_ROOT>\translation_manifest.json
目标语言：zh-CN
覆盖模式：standalone
~~~

点击“保存”，保存为 `<WORK_ROOT>\project.json`。保存 profile 只写 JSON，不修改源 PAK 或游戏目录。

### 1.2 导出和编辑 CSV

在“翻译”页点击“导出 CSV”。该动作只读取源 PAK。如果目标 CSV 已存在，选择“否”会保留原文件，只有明确选择“是”才会覆盖。

用支持 UTF-8 的表格工具打开 CSV，只修改 `translation` 列。保持 resource_id、source_path、text_key、original_text、original_hash 和 status 不变；译文中的 `{name}`、`%s` 等占位符必须与原文匹配。

### 1.3 Dry-run、构建和检查

回到 GUI 点击“预演”，确认源路径、键、原文和译文。确认后点击“构建翻译 PAK + Manifest”。输出只写入工作目录，源 PAK 不会被覆盖。

构建后可以在“PAK”页列出输出包，或提取 JSON 检查译文。没有确认前不要安装到游戏目录。

### 1.4 安装和回滚

在“安装 / 回滚”页填写目标根目录、备份目录、安装记录和文件映射。文件字段格式为：

~~~text
<WORK_ROOT>\translation_overlay.pak=Assets\translation_overlay.pak
~~~

先点“安装预演”，确认目标是根目录内的相对路径，再点击“安装…”并确认。验证项目效果后，需要撤销时点击“回滚…”。工具会验证备份哈希后恢复或删除文件。

## 2. 全量字体（ID 1–20）

1. 将 `<UI_PAK>` 临时填入源 PAK，在“PAK”页提取 `gfxfontlib.gfx` 到 `<WORK_ROOT>\ui_extract`；完成后恢复翻译用的源 PAK。
2. 在“字体”页填写提取出的 GFX 和 `<FFDEC_CLI>`，点击“扫描 GFX”，以实际发现的 character_id 为准。
3. 用 `<FONT_FILE>` 和 UTF-8 字符集文件执行“检查覆盖率”，只有 `missing` 为空列表时才继续。
4. 输出 GFX 填 `<WORK_ROOT>\font_full.gfx`，字体输出 PAK 填 `<WORK_ROOT>\font_full.pak`，槽位填写每个要替换的 `ID=<FONT_FILE>`；全量方案通常列出 ID 1–20。
5. 点击“替换槽位”，再点击“构建字体 PAK”。输出 PAK 应该只有 `Libs/UI/exported_files/gfxfontlib.gfx`。

## 3. 子集字体

1. 在“字体”页填写完整字体、字符集文件和子集输出字体 `<WORK_ROOT>\font_subset.ttf`。
2. “fontTools 自定义 Python（可选）”留空即可使用内置 fontTools；点击“创建子集字体”。
3. 将覆盖率字体临时改为子集 TTF，再次检查覆盖率，确认 `missing` 为空。
4. 将槽位改为需要的映射，例如 `7=<WORK_ROOT>\font_subset.ttf;16=<WORK_ROOT>\font_subset.ttf`，然后替换槽位并构建字体 PAK。
5. 在“PAK”页确认字体 PAK 只有一个 GFX 条目，再按翻译 PAK 的方式执行安装预演、安装、游戏验证和回滚。

## 4. 常见错误

- `FFDec is unavailable`：确认填写的是能接受 `-dumpSWF` 和 `-replace` 参数的 `ffdec-cli.exe`，不是图形启动器，也没有误填到输出 GFX。
- `WinError 123`：检查路径字段是否混入 Markdown 链接、括号、反引号或换行；文件字段必须是纯文本的 `SOURCE=RELATIVE_DEST` 映射。
- EXE 构建 `WinError 5`：关闭正在运行的 CryEngineLocalization.exe 后再构建。
- 中文变成缺字方框：重新收集实际字符并检查覆盖率，必要时增加子集槽位或改用全量字体。

## 5. CLI 对照

~~~powershell
cry-localize profile init --output project.json
cry-localize workflow export-csv project.json
cry-localize workflow dry-run project.json
cry-localize workflow build project.json
cry-localize workflow install project.json --dry-run
cry-localize workflow install project.json
cry-localize workflow rollback project.json
~~~

GUI 和 CLI 共用同一套核心；完整 profile 字段见 integrated-gui-cli-guide.md，字体命令见 fonts.md。
