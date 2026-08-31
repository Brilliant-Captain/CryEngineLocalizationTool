# CryEngine 字体流程

字体流程分为全量字体和子集字体，两者都不会修改源 `UI.pak` 或源 GFX。

## 全量字体

全量方案直接使用完整的 TTF/OTF 替换指定槽位（例如 ID 1–20），覆盖范围最大，生成的 GFX/PAK 通常更大，也会让更多界面采用替换字体。

GUI 顺序：

1. 在 PAK 页从真实 `UI.pak` 提取 `gfxfontlib.gfx`。
2. 在 Fonts 页扫描 GFX，确认目标 `character_id`。
3. 用字符集文件执行覆盖率检查，确认 `missing` 为空。
4. 勾选字体替换，填写源/输出 GFX、FFDec、字体 PAK 和槽位映射（例如 `1=FONT;…;20=FONT`）。
5. 点击“替换槽位”，再点击“构建字体 PAK”。
6. 用 PAK 页确认字体 PAK 只有 `Libs/UI/exported_files/gfxfontlib.gfx`。

## 子集字体

子集方案先从完整字体生成只包含字符集文件中文字形的较小 TTF，再用这个子集 TTF 替换槽位。它适合只需要少量语言文本的项目，体积更小，但字符集文件遗漏的字会变成缺字方框。

GUI 顺序：

1. 先完成 GFX 提取、扫描和覆盖率检查。
2. `覆盖率字体` 填完整字体，`字符集文件` 填 UTF-8 文本。
3. `子集输出字体` 填新路径，例如 `work\font_subset.ttf`。
4. 点击“创建子集字体”，确认输出文件存在。
5. 将槽位映射中的字体文件改为生成的 `font_subset.ttf`，可只替换需要的槽位，也可配置 ID 1–20。
6. 点击“替换槽位”，再构建字体 PAK。

fontTools 默认由 GUI/CLI 内置调用，通常不需要填写 Python。若要使用某个自定义环境，可在 Custom Python for fontTools 中填写解释器，或在 CLI 传入 --python；显式路径会优先于内置调用。

## CLI 等价命令

```powershell
cry-localize font scan gfxfontlib.gfx --ffdec <FFDEC_CLI>
cry-localize font coverage <FULL_FONT> characters.txt --python <PYTHON>
cry-localize font subset <FULL_FONT> characters.txt --output-font work\font_subset.ttf --python <PYTHON>
cry-localize font replace gfxfontlib.gfx --output-gfx work\patched.gfx --ffdec <FFDEC_CLI> --slot 7=work\font_subset.ttf --slot 16=work\font_subset.ttf
cry-localize pak build work\font_overlay work\font_overlay.pak
```

不要把 FFDec GUI launcher 当作 CLI；必须填写能够接受 `-dumpSWF`/`-replace` 参数的 `ffdec-cli.exe`。

## 旧式 GFX 安全评估与原位移植

FFDec 的 `-replace` 会重建整个 GFX。旧版或预加载的 Scaleform 文件可能在游戏运行时崩溃，即使 FFDec 能重新解析输出。先执行安全评估：

```powershell
cry-localize font assess <INPUT_GFX>
cry-localize font assess <INPUT_GFX> --candidate <FFDEC_CANDIDATE_GFX>
```

报告会给出 `safe`、`caution` 或 `blocked`，并说明文件体积增长、字体占比、非字体 tag 改动等原因。`blocked` 表示不应直接把 FFDec 候选安装到游戏中。

对于需要保留旧版 GFX 时间轴和布局的文件，使用原位移植：

```powershell
cry-localize font migrate <INPUT_GFX> `
  --output-gfx <OUTPUT_GFX> `
  --ffdec <FFDEC_CLI> `
  --slot 1=<FONT_FILE>
```

工具只在临时目录调用 FFDec 生成候选，然后从候选中提取指定 `DefineFont3` tag，写回原版 GFX；原版的非字体 tag、导出表、脚本和时间轴会被保留。也可以提供 `--candidate` 跳过候选生成，直接移植一个已生成的候选：

```powershell
cry-localize font migrate <INPUT_GFX> `
  --candidate <CANDIDATE_GFX> `
  --output-gfx <OUTPUT_GFX> `
  --slot 1=<FONT_FILE>
```

原位移植仍需在目标游戏中手工验证；如果 GFX tag 顺序或容器头不一致，工具会拒绝输出。
