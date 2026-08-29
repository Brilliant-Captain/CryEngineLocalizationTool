# War of Rights 适配器

## 已验证约定

- 官方本地化路径为 `Localization/english/*.json`。
- 实测：`Localization/Finnish/*` 加 Finnish 配置未被主菜单采用；English 配置下的独立 English-path overlay PAK 可以覆盖主菜单文本。
- 部分 JSON 使用尾逗号，目录解析必须使用兼容解析器。
- 菜单 GFX 引用 `gfxfontlib.gfx`；已验证常用 DefineFont3 槽位为字符 ID 7（`Type No. 12 WF`）和 ID 16（`Type No. 2 WF`）。
- 语言配置使用 `g_language` 与 `Localization.Language`；命令行参数优先于 `autoexec.cfg`，配置优先于默认值。

## 安全流程

1. 确认游戏进程已退出。
2. 读取并记录源 PAK/config 的大小和 SHA-256。
3. 通过 dry-run 检查 English 路径冲突和翻译状态。
4. 输出到自定义 staging/安装目录；不要直接覆盖源文件。
5. 用户确认后才复制补丁，并保留 `BackupRecord` 供恢复。

War of Rights 的可用方案是显式 English-path overlay：把翻译文件放入独立 PAK 的 `Localization/english/` 路径，并让补丁 PAK 文件名排在官方包之后（例如 `zzz_...pak`），在 manifest 中记录 `overlay_mode=english-path-overlay`、源包哈希和替换路径。默认安全 API 仍会拒绝未声明用途的重复路径；只有用户明确选择 overlay 模式时才允许该冲突。

## 外部依赖

GFX 字体替换需要用户本机的 FFDec CLI；自定义字集需要带 `fontTools.subset` 的 Python。贴图输入为 PNG/PPM 时无需额外依赖，项目内置纯 Python DXT5 编码；其它图片格式可选 Pillow，FFmpeg 可用于额外解码验证。缺少可选依赖时 CLI 必须停止并说明安装/配置方式，不得静默跳过。
