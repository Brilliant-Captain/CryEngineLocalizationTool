# CryEngine Localization

安全、可回滚的 CryEngine 本地化工具。GUI 工作台与 CLI 共享同一套核心和项目 profile，适用于通用 CryEngine 项目；War of Rights、Scaleform GFX 字体和 DDS 贴图都是可选适配器。

Windows 用户可以从 [GitHub Releases](https://github.com/Brilliant-Captain/CryEngineLocalizationTool/releases) 下载窗口版 `CryEngineLocalization.exe`、控制台版 `cry-localize.exe` 和 SHA-256 清单。

## 范围与安全

- 只处理 CryEngine 项目和 ZIP 风格 PAK；支持 JSON 以及旧式 Excel SpreadsheetML XML 本地化表，不提供 Unreal 或其它引擎适配器。
- 仓库不包含商业游戏 PAK、解包目录、用户字体或本机构建产物。
- 默认执行 dry-run；修改游戏安装前必须生成带 SHA-256 的备份。
- 官方 `Localization/english/` 路径不会被重复覆盖，避免引擎加载冲突。

## 从源码运行

```powershell
python -m pip install -e ".[test,fonts,textures]"
python -m pytest -q
cry-localize --help
```

核心图像编码使用 Python 标准库；`fonts` extra 提供 fontTools，`textures` extra 为 PNG/PSD 等额外格式提供 Pillow。GFX 写回需要单独安装 FFDec CLI；`cry-localize tools doctor` 会自动探测解释器和工具。工具路径通过命令行参数或环境配置显式传入，不会写入 manifest 或源代码。

## CLI 示例

```powershell
cry-localize identify <PROJECT_ROOT>
cry-localize pak list <GAME_ROOT>\Assets\GameData.pak
cry-localize pak discover-key <GAME_ROOT> --output public.der
cry-localize pak decrypt <INPUT_PAK> <OUTPUT_PAK> --public-key public.der
cry-localize pak decrypt <INPUT_PAK> <OUTPUT_PAK> --game-root <GAME_ROOT>
cry-localize pak decrypt-tree <INPUT_ROOT> <OUTPUT_ROOT> --public-key <PUBLIC_DER> --mode pak
cry-localize pak decrypt-tree <INPUT_ROOT> <OUTPUT_ROOT> --game-root <GAME_ROOT> --mode pak
cry-localize pak decrypt-tree <INPUT_ROOT> <OUTPUT_ROOT> --public-key <PUBLIC_DER> --mode extract --report decrypt-report.json
cry-localize catalog export <GAME_ROOT>\Assets\GameData.pak --output translations.csv
cry-localize catalog export-friendly <GAME_ROOT>\Assets\GameData.pak --output translation-work.csv
cry-localize profile init --output project.json
cry-localize workflow export-csv project.json
cry-localize workflow dry-run project.json
cry-localize workflow build project.json
cry-localize workflow batch-scan batch-project.json
cry-localize workflow batch-reuse-old batch-project.json --dry-run
cry-localize workflow batch-reuse-old batch-project.json
cry-localize workflow batch-dry-run batch-project.json
cry-localize workflow batch-build-translation batch-project.json
cry-localize workflow batch-build-font batch-project.json
cry-localize workflow batch-build batch-project.json
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

`workflow batch-scan --friendly` 和 `catalog export-friendly` 会额外输出 `source_text` 与空白的 `target_translation`。`source_text` 优先采用 XML 已有的 `TRANSLATED TEXT`，否则采用 `ORIGINAL TEXT`；填写 `target_translation` 后，现有 `apply`、`build` 和批量构建流程会把它写回原始 `TRANSLATED TEXT` 列，同时继续校验 `original_text` 与 `original_hash`。

`apply` 的非 dry-run 模式只写新的输出 PAK；源包保持不变。旧式 CryEngine PAK 中中央目录 `/` 与本地头 `\` 的路径差异会在安全规范化、大小和 CRC 校验后兼容读取。War of Rights 的加载约定、配置备份和字体/贴图依赖说明见 [适配器文档](docs/adapters/war-of-rights.md)。

`CryEngineLocalization.exe` 是完整的 Tkinter 工作台；`cry-localize.exe` 是同一套源码构建的 console CLI。两者都支持通用 project profile；在无图形环境时使用 CLI。

`identify` 会分别报告精确引擎版本、版本证据来源和代际提示。`.cryproject` 版本优先；完整 Windows 游戏目录可读取 `CrySystem.dll` 文件版本；只有旧式 XML/GFX 资源时仅提示 `CryEngine 2/3-era`，不会猜测精确版本号。

需要独立 Windows 程序时，参见 [Windows 发布说明](docs/releasing.md)。GitHub Release 会提供不含游戏资源的 `CryEngineLocalization.exe`、`cry-localize.exe` 和 SHA-256 清单。

完整的安装、GUI、CSV、War of Rights overlay、字体、回滚和故障排除步骤见 [详细使用手册](docs/usage.md)。

通用 GUI/CLI profile 流程见 [一体化使用指南](docs/integrated-gui-cli-guide.md)。

按真实项目整理的 GUI 操作步骤见 [GUI 操作教程](docs/gui-operation-tutorial.md)。

界面默认使用简体中文，其他语言可通过外部 JSON 语言包添加；见 [GUI 界面本地化指南](docs/ui-localization.md)。

字体全量/子集流程见 [字体流程指南](docs/fonts.md)。

全游戏资源扫描、人工翻译 CSV 与批量字体 overlay 见 [批量资源工作流](docs/adapters/batch-resource-localization.md)。GFX 非字体字符串只会进入 `report-only` 查漏记录，工具不会回写它们。

如果 FFDec 已加入 PATH 或设置了 `FFDEC_CLI` 环境变量，`font scan/replace` 可以省略 `--ffdec`。
### 加密 CryEngine PAK

`pak decrypt` 使用 libcrypak 兼容后端处理 CryEngine 原生加密 PAK。普通 ZIP 风格 PAK 会直接复制并校验；加密 PAK 会解密为可读取的 ZIP 风格 PAK。`decrypt-tree` 递归扫描输入目录，`--mode pak` 保持每个 `.pak` 的相对路径，`--mode extract` 将成员展开到同名目录，并可用 `--report` 写出逐文件 SHA-256、条目数和失败原因。

源码运行时可通过 `--decryptor` 指定后端，或设置 `CRYENGINE_PAK_DECRYPTOR`。Windows 发行版将后端放在 `resources/bin/cry-pak-decrypt.exe`，用户无需安装 libtomcrypt、libtommath、CMake 或编译器。`pak discover-key` 会扫描用户指定游戏目录中的 EXE/DLL，提取嵌入的 CryEngine RSA DER，并写入用户指定的公钥文件；也可通过 `--public-key` 或 `CRYENGINE_PAK_PUBLIC_KEY` 直接提供已有公钥。
