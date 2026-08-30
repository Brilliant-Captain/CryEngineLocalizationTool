# CryEngine 一体化 GUI/CLI 使用指南

本工具面向通用 CryEngine 项目。GUI 与 CLI 共用同一套核心逻辑和项目 profile；不自动选择游戏目录，也不假设 War of Rights、PAK 文件名或进程名。你的项目路径、语言、overlay 策略和外部工具路径都由 profile 明确提供。

## 1. 两个入口

- `CryEngineLocalization.exe`：窗口版工作台，双击后按页签完成项目配置、CSV 导出、Dry-run、PAK/字体构建、安装和回滚。
- `cry-localize.exe` 或 `cry-localize`：控制台入口，保留所有原有命令，并增加 profile/workflow 命令，适合批处理和 CI。

两个入口读取相同的 JSON profile，也可以继续使用原有的显式路径命令。

界面语言由独立 JSON 资源驱动，默认是 `zh-CN`；新增语言和外部语言目录的完整方法见 [GUI 界面本地化指南](ui-localization.md)。

## 2. 项目 profile

先在 GUI 中点击 `New`，填写项目名称、源 PAK、CSV 路径、输出 PAK、manifest、语言和 overlay 模式，然后保存为例如 `project.json`。也可以运行：

```powershell
cry-localize profile init --output project.json
```

编辑后用以下命令检查：

```powershell
cry-localize profile validate project.json
cry-localize profile show project.json
```

最小配置示例：

```json
{
  "schema_version": 1,
  "name": "Example CryEngine Project",
  "engine_version": "5.6",
  "source_pak": "D:/Project/Assets/GameData.pak",
  "translation_csv": "D:/Project/work/translations.csv",
  "output_pak": "D:/Project/work/translation_overlay.pak",
  "manifest": "D:/Project/work/translation_manifest.json",
  "language": "zh-CN",
  "ui_language": "zh-CN",
  "overlay_mode": "standalone",
  "font": {
    "enabled": false,
    "source_gfx": "",
    "output_gfx": "",
    "ffdec": "",
    "python": "",
    "output_pak": "",
    "coverage_font": "",
    "coverage_text": "",
    "subset_output_font": "",
    "slots": []
  },
  "install": {
    "game_root": "",
    "backup_dir": "",
    "record": "",
    "files": [],
    "process_names": []
  }
}
```

`overlay_mode` 只能是 `standalone` 或 `english-path-overlay`。后者只应用 `Localization/english/` 条目，适用于需要以原 English 路径覆盖加载的项目；不要在没有确认引擎加载顺序时启用它。

## 3. GUI 完整流程

1. 在 `Project` 页填写并保存 profile。所有路径由用户选择，工具不会自动探测某个特定游戏。
2. 在 `Translation` 页点击 `Export CSV`。该动作只读取源 PAK，不写游戏目录。
3. 用表格工具只编辑 CSV 的 `translation` 列，保持原文、resource ID 和哈希不变。
4. 再次点击 `Export CSV` 时，如果目标 CSV 已存在，GUI 会停止并要求明确确认；拒绝确认时原文件保持不变。
5. 点击 `Dry-run`，检查变更数量、源路径、原文和译文。
6. 点击 `Build Translation PAK + Manifest`，生成 profile 中指定的输出文件。
7. 在 `Fonts` 页执行 GFX 扫描、覆盖率检查、槽位替换和字体 PAK 构建。全量替换时可以在槽位输入中配置 ID 1–20。
8. 在 `PAK` 页执行条目列表或安全提取，用于检查生成物。
9. 在 `Install / Rollback` 页先执行 Install Dry-run；确认目标和备份目录后点击 `Install…`。安装前还会再次弹出确认，并使用 profile 中配置的进程名检查运行状态。
10. 需要撤销时点击 `Rollback…`，工具会验证安装记录和备份哈希后恢复文件。

## 4. CLI 等价流程

使用 profile 时：

```powershell
cry-localize workflow export-csv project.json
# 如果 CSV 已存在，必须明确传入：
cry-localize workflow export-csv project.json --overwrite

cry-localize workflow dry-run project.json
cry-localize workflow build project.json
cry-localize workflow install project.json --dry-run
cry-localize workflow install project.json
cry-localize workflow rollback project.json
```

不使用 profile 时，旧命令仍然有效：

```powershell
cry-localize catalog export <SOURCE_PAK> --output <CSV>
cry-localize apply <CSV> --dry-run
cry-localize build <SOURCE_PAK> <CSV> --output-pak <OUTPUT_PAK> --manifest <MANIFEST> --language <LANGUAGE>
cry-localize pak list <PAK>
cry-localize font scan <GFX> --ffdec <FFDEC_CLI>
cry-localize font replace <GFX> --output-gfx <OUTPUT_GFX> --slot <ID>=<FONT_FILE>
```

## 5. 安全边界

- CSV 导出、profile 校验、Dry-run、PAK 列表和提取不会修改游戏目录。
- 翻译构建始终写新的 PAK，源 PAK 不变。
- 安装需要显式操作，并为已有目标创建带哈希验证的备份。
- 安装目标必须是配置根目录内的相对路径；路径遍历会失败。
- FFDec 和字体文件由用户提供；fontTools 已内置在发布 EXE 中，也可以用自定义 Python 覆盖。
- 测试 PAK 与正式 PAK 应使用不同目录或名称；安装正式文件前先移出旧测试覆盖包。
