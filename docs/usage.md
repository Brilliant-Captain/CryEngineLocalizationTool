# CryEngine Localization 使用手册

本手册针对 `v0.2.0`。工具只处理 CryEngine 项目和 ZIP 风格 PAK。War of Rights 已实测的可用翻译方式是 English-path overlay：翻译文件仍使用 `Localization/english/` 路径，但放在一个排序靠后的独立 PAK 中。

## 1. 安装

### 从源码运行

建议使用项目自己的虚拟环境：

```powershell
Set-Location <PROJECT_ROOT>
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test,fonts,textures]"
.\.venv\Scripts\python.exe -m pytest -q
```

`fonts` 安装 fontTools，`textures` 安装 Pillow。PNG/PPM→DXT5 编码不依赖 Pillow；GFX 写回仍需要用户自行取得 FFDec CLI。可以把 FFDec 加入 PATH，或设置：

```powershell
$env:FFDEC_CLI = <FFDEC_CLI>
```

检查工具：

```powershell
cry-localize tools doctor
```

### 使用独立 EXE

从 GitHub Release 下载 `CryEngineLocalization.exe` 和 `SHA256SUMS.json`，先核对 SHA-256。EXE 是 one-file Tkinter GUI，不包含任何游戏资源、字体或 FFDec。双击 EXE 即可打开窗口；若 Windows SmartScreen 提示未知发布者，请核对哈希后再决定是否运行。

## 2. GUI 工作流

1. 启动 `CryEngineLocalization.exe`，或运行 `cry-localize gui`。
2. 选择源 PAK，例如 `Assets\GameData.pak`。
3. 先用 CLI 导出 CSV（GUI 当前主要负责 dry-run/build）：

   ```powershell
   cry-localize catalog export <GAME_ROOT>\Assets\GameData.pak --output translations.csv
   ```

4. 在表格中只填写 `translation` 列，保存为 UTF-8 CSV。
5. 在 GUI 选择源 PAK、CSV、输出 PAK 和 manifest，填写 `zh-CN`。
6. 先点击 Dry-run，确认变更数量和原文；再点击 Build PAK + Manifest。
7. 生成的 PAK 应使用排序靠后的文件名，例如 `zzz_WoR_CN_Localization.pak`。
8. GUI 不会自动覆盖游戏文件；确认无误后使用第 5 节的安装事务。

## 3. CLI 基本流程

### 3.1 识别项目与查看 PAK

```powershell
cry-localize identify <PROJECT_ROOT>
cry-localize pak list <GAME_ROOT>\Assets\GameData.pak
cry-localize pak extract <GAME_ROOT>\Assets\UI.pak <TEMP_ROOT>\UI --match gfxfontlib.gfx
```

`identify` 输出 CryEngine 置信度和 PAK 列表。`extract` 的输出根目录必须是临时目录或用户明确指定的工作目录，工具会拒绝路径遍历。

### 3.2 导出和编辑翻译表

```powershell
cry-localize catalog export <GAME_ROOT>\Assets\GameData.pak --output work\translations.csv
```

CSV 列含义：

| 列 | 是否可编辑 | 说明 |
|---|---:|---|
| `resource_id` | 否 | `source_path:text_key` 的稳定 ID |
| `source_path` | 否 | PAK 内部 JSON 路径 |
| `text_key` | 否 | CryEngine `Localizations[].key` 或嵌套路径 |
| `original_text` | 否 | 导出时的原文 |
| `original_hash` | 否 | 原文 UTF-8 SHA-256 |
| `translation` | 是 | 译文；空值表示不替换 |
| `status` | 否 | `active/new/stale/orphaned/invalid` |

不要修改原文列、ID 或哈希。译文中的 `{name}`、`%s` 等占位符必须与原文完全匹配。HTML 标签可以翻译文字，但不要删除引擎需要的占位符。

游戏更新后重新导出目录，并在应用前比较 `original_hash`。哈希变化会变成 `stale` 并清空旧译文，删除的资源变成 `orphaned`，不会静默写回旧文本。

### 3.3 Dry-run 和构建

```powershell
cry-localize apply work\translations.csv --dry-run

cry-localize build <GAME_ROOT>\Assets\GameData.pak work\translations.csv `
  --output-pak work\zzz_WoR_CN_Localization.pak `
  --manifest work\manifest.json `
  --language zh-CN `
  --project WarOfRights `
  --overlay-mode english-path-overlay
```

`build` 会检查 CSV 中的原文哈希与当前源包一致，然后写出新 PAK。源 PAK 不会被覆盖。manifest 至少记录源包文件名和 SHA-256、替换项、目标语言、覆盖模式、字体方案和输出哈希。

## 4. War of Rights 翻译流程

### 4.1 为什么使用 English-path overlay

实测 `Localization/Finnish/*` 配合 Finnish 配置不会被主菜单采用；而 `Localization/english/MainMenu.json` 放在排序靠后的 PAK 中可以覆盖官方文本。因此：

- `g_language` 保持 `english`；
- 翻译 PAK 内部路径保持 `Localization/english/*.json`；
- PAK 文件名使用 `zzz_` 等排序靠后的前缀；
- manifest 使用 `overlay_mode=english-path-overlay`；
- 不要同时放置多个未声明用途的重复 English overlay。

### 4.2 安装前检查

确认游戏已退出，并检查源文件哈希：

```powershell
cry-localize tools doctor
cry-localize identify <GAME_ROOT>
Get-FileHash <GAME_ROOT>\Assets\GameData.pak -Algorithm SHA256
```

如果要生成语言配置文件，不要直接改游戏目录：

```powershell
cry-localize config preview <GAME_ROOT>\autoexec.cfg --language english
cry-localize config write <GAME_ROOT>\autoexec.cfg `
  --output work\autoexec.cfg `
  --language english
```

### 4.3 Dry-run 安装和实际安装

先只安装 overlay PAK：

```powershell
cry-localize install `
  --game-root <GAME_ROOT> `
  --backup-dir work\backup `
  --record work\install.json `
  --file work\zzz_WoR_CN_Localization.pak=Assets\zzz_WoR_CN_Localization.pak `
  --dry-run
```

确认输出目标、源哈希和备份信息无误后，去掉 `--dry-run`：

```powershell
cry-localize install `
  --game-root <GAME_ROOT> `
  --backup-dir work\backup `
  --record work\install.json `
  --file work\zzz_WoR_CN_Localization.pak=Assets\zzz_WoR_CN_Localization.pak
```

需要同时安装字体 GFX 时，再增加一个 `--file`，例如：

```powershell
--file work\gfxfontlib.patched.gfx=Assets\Libs\UI\exported_files\gfxfontlib.gfx
```

安装事务会检查 War of Rights 进程、拒绝越界目标、备份已存在文件，并用临时文件原子替换。失败时会自动恢复已经写入的项目。

### 4.4 启动和验证

不要直接双击 `WarOfRights.exe`，否则可能出现 Steam 初始化失败。使用 Steam：

```powershell
Start-Process 'steam://rungameid/424030'
```

进入主菜单，检查目标文本。确认成功后退出游戏；如果失败，先不要继续改 PAK，读取日志并回滚。

### 4.5 回滚

```powershell
cry-localize rollback work\install.json
```

回滚会验证 record 中的 game root、backup root 和 SHA-256。新增文件会被删除，原有文件会恢复。回滚后应再次运行 `Get-FileHash` 确认源文件恢复。

## 5. 字体流程

### 5.1 扫描槽位

```powershell
cry-localize pak extract <GAME_ROOT>\Assets\UI.pak <TEMP_ROOT>\UI --match gfxfontlib.gfx
cry-localize font scan <TEMP_ROOT>\UI\Libs\UI\exported_files\gfxfontlib.gfx --ffdec <FFDEC_CLI>
```

War of Rights 当前验证过的主菜单槽位是 ID 7（`Type No. 12 WF`）和 ID 16（`Type No. 2 WF`）。不要把旧脚本中的 ID 10/2 当成固定值，必须以扫描结果为准。

### 5.2 覆盖率和子集

```powershell
cry-localize font coverage <REGULAR_FONT> work\translation-chars.txt
cry-localize font subset <REGULAR_FONT> work\translation-chars.txt --output-font work\regular-subset.ttf
```

`translation-chars.txt` 应由实际译文和 UI 文本合并生成。覆盖率输出的 `missing` 不为空时不要继续嵌入；先更换字体或补齐字形。

### 5.3 替换 GFX 字体

```powershell
cry-localize font replace <TEMP_ROOT>\gfxfontlib.gfx `
  --output-gfx work\gfxfontlib.patched.gfx `
  --ffdec <FFDEC_CLI> `
  --slot 7=<REGULAR_FONT> `
  --slot 16=<BOLD_FONT>
```

输出 GFX 必须与输入不同。完成后把它作为独立安装项加入 manifest；不要把字体文件本身提交到 GitHub。

## 6. DDS 贴图命令（可选）

翻译验证通过后再处理贴图。当前支持：

```powershell
cry-localize texture inspect menu.dds
cry-localize texture encode menu.png --output-dds work\menu.dds
cry-localize texture replace <SOURCE_PAK> <INTERNAL_DDS_PATH> work\menu.dds `
  --output-pak work\textures.pak
```

编码器会生成 DXT5 和完整 MIP 链。替换前会拦截尺寸、MIP、FourCC 和 Alpha 不兼容；贴图替换仍建议先在独立 PAK 和临时安装目录验证。

## 7. 常见问题

### 主菜单仍是英文

确认 PAK 文件名排在官方包之后、内部路径是 `Localization/english/`、配置仍为 English，并且通过 Steam 启动。Finnish 路径映射已验证不会被主菜单采用。

### `source changed since catalog export`

源 PAK 已更新或 CSV 原文列被修改。重新导出 CSV，重新翻译，并保留新的 `original_hash`。

### `FFDec is unavailable`

把 FFDec CLI 加入 PATH，设置 `FFDEC_CLI`，或为 `font scan/replace` 传入 `--ffdec`。FFDec 不随项目 EXE 分发。

### `fontTools is unavailable`

安装字体 extra：

```powershell
python -m pip install -e ".[fonts]"
```

也可以通过 `--python` 指定带 `fontTools.subset` 的 Python。

### Steam 初始化失败

不要直接运行游戏 EXE；启动 Steam 客户端后使用 `steam://rungameid/424030`。

### GitHub 仓库出现大文件或本机路径

确认 `release/`、`output/`、PAK/GFX/DDS/字体均被 `.gitignore` 忽略；运行：

```powershell
git ls-files | Select-String -Pattern '\.(pak|gfx|dds|ttf|otf|ttc)$'
rg -n -i '<DRIVE>:\\Users|steamapps|AppData|<GAME_ROOT>' --glob '!.git/**' .
```
