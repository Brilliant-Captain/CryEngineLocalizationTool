# CryEngine Localization

安全、可回滚的 CryEngine 本地化工具。GUI 工作台与 CLI 共享同一套核心和项目 profile，适用于通用 CryEngine 项目；War of Rights、Scaleform GFX 字体和 DDS 贴图都是可选适配器。

## 范围与安全

- 只处理 CryEngine 项目和 ZIP 风格 PAK；不提供 Unreal 或其它引擎适配器。
- 商业游戏 PAK、解包目录、用户字体和构建产物都是本地输入，禁止提交到仓库。
- 默认执行 dry-run；修改游戏安装前必须生成带 SHA-256 的备份。
- 官方 `Localization/english/` 路径不会被重复覆盖，避免引擎加载冲突。

## 开发

```powershell
python -m pip install -e ".[test,fonts,textures]"
python -m pytest -q
cry-localize --help
```

核心图像编码使用 Python 标准库；`fonts` extra 提供 fontTools，`textures` extra 为 PNG/PSD 等额外格式提供 Pillow。GFX 写回仍需要用户本机的 FFDec CLI（不可将其商业/反编译工具打进仓库）；`cry-localize tools doctor` 会自动探测解释器和工具。工具路径通过命令行参数或环境配置显式传入，不会把用户机器路径写入 manifest 或源代码。

## CLI 示例

```powershell
cry-localize identify <PROJECT_ROOT>
cry-localize pak list <GAME_ROOT>\Assets\GameData.pak
cry-localize catalog export <GAME_ROOT>\Assets\GameData.pak --output translations.csv
cry-localize profile init --output project.json
cry-localize workflow export-csv project.json
cry-localize workflow dry-run project.json
cry-localize workflow build project.json
cry-localize apply translations.csv --dry-run
cry-localize apply translations.csv --source-pak GameData.pak --output-pak output\GameData.pak
cry-localize font scan gfxfontlib.gfx --ffdec <FFDEC_CLI>
cry-localize font replace gfxfontlib.gfx --output-gfx output\gfxfontlib.gfx --ffdec <FFDEC_CLI> --slot 7=<REGULAR_FONT> --slot 16=<BOLD_FONT>
cry-localize font coverage <REGULAR_FONT> translation-text.txt
cry-localize font subset <REGULAR_FONT> translation-text.txt --output-font output\regular-subset.ttf
cry-localize texture inspect menu.dds
cry-localize texture encode menu.png --output-dds output\menu.dds
cry-localize config preview autoexec.cfg --language english
cry-localize config write autoexec.cfg --output output\autoexec.cfg --language english
cry-localize install --game-root <GAME_ROOT> --backup-dir backups --record install.json --file output\GameData.pak=Assets\GameData.pak --dry-run
cry-localize install --game-root <GAME_ROOT> --backup-dir backups --record install.json --file output\GameData.pak=Assets\GameData.pak
cry-localize rollback install.json
cry-localize gui
```

`apply` 的非 dry-run 模式只写新的输出 PAK；源包保持不变。War of Rights 的直接安装、配置备份和字体/贴图依赖说明见 `docs/adapters/war-of-rights.md`。

`CryEngineLocalization.exe` 是完整的 Tkinter 工作台；`cry-localize.exe` 是同一套源码构建的 console CLI。两者都支持通用 project profile；在无图形环境时使用 CLI。

需要独立 Windows 程序时，参见 [Windows 发布说明](docs/releasing.md)。GitHub Release 会提供不含游戏资源的 `CryEngineLocalization.exe`、`cry-localize.exe` 和 SHA-256 清单。

完整的安装、GUI、CSV、War of Rights overlay、字体、回滚和故障排除步骤见 [详细使用手册](docs/usage.md)。

通用 GUI/CLI profile 流程见 [一体化使用指南](docs/integrated-gui-cli-guide.md)。

按真实项目整理的 GUI 操作步骤见 [GUI 操作教程](docs/gui-operation-tutorial.md)。

界面默认使用简体中文，其他语言可通过外部 JSON 语言包添加；见 [GUI 界面本地化指南](docs/ui-localization.md)。

字体全量/子集流程见 [字体流程指南](docs/fonts.md)。



如果 FFDec 已加入 PATH 或设置了 `FFDEC_CLI` 环境变量，`font scan/replace` 可以省略 `--ffdec`。
