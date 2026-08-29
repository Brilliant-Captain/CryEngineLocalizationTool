# CryEngine Localization

安全、可回滚的 CryEngine 本地化工具。项目当前处于早期开发阶段，先提供可测试的 CLI 核心，再逐步接入 War of Rights、Scaleform GFX 字体和 DDS 贴图适配器。

## 范围与安全

- 只处理 CryEngine 项目和 ZIP 风格 PAK；不提供 Unreal 或其它引擎适配器。
- 商业游戏 PAK、解包目录、用户字体和构建产物都是本地输入，禁止提交到仓库。
- 默认执行 dry-run；修改游戏安装前必须生成带 SHA-256 的备份。
- 官方 `Localization/english/` 路径不会被重复覆盖，避免引擎加载冲突。

## 开发

```powershell
python -m pip install -e ".[test]"
python -m pytest -q
cry-localize --help
```

核心依赖只使用 Python 标准库。DDS 处理可选安装 Pillow；字体子集需要 fontTools 和外部 FFDec CLI。工具路径通过命令行参数或配置显式传入，不会把用户机器路径写入 manifest 或源代码。

## CLI 示例

```powershell
cry-localize identify C:\path\to\cryengine-project
cry-localize pak list C:\path\to\Assets\GameData.pak
cry-localize catalog export C:\path\to\Assets\GameData.pak --output translations.csv
cry-localize apply translations.csv --dry-run
cry-localize apply translations.csv --source-pak GameData.pak --output-pak output\GameData.pak
cry-localize font scan gfxfontlib.gfx --ffdec C:\tools\ffdec-cli.exe
cry-localize texture inspect menu.dds
cry-localize config preview autoexec.cfg --language english
```

`apply` 的非 dry-run 模式只写新的输出 PAK；源包保持不变。War of Rights 的直接安装、配置备份和字体/贴图依赖说明见 `docs/adapters/war-of-rights.md`。
