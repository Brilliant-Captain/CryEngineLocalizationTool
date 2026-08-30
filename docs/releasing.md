# 发布 Windows GUI 与 CLI

仓库不提交 `.exe`、PAK、GFX、DDS 或字体。推送版本标签后，GitHub Actions 会在 Windows runner 上从同一套源码构建窗口版 `CryEngineLocalization.exe` 和控制台版 `cry-localize.exe`，上传构建 artifact，并把两个 EXE 与 `SHA256SUMS.json` 附加到对应 Release。

本地构建：

```powershell
python -m pip install -e ".[test,fonts,textures]"
python -m pip install -e ".[build]"
.\scripts\build_exe.ps1 -OutputDir .\release
```

构建脚本会检查 PyInstaller 和 fontTools；fontTools 必须安装，因为它会被内置到两个 EXE 中。

输出目录包含：

- `CryEngineLocalization.exe`：one-file、windowed Tkinter GUI；启动后直接显示窗口，不打开控制台。
- `cry-localize.exe`：one-file、console CLI；支持全部原有命令和 profile/workflow 命令。
- `SHA256SUMS.json`：两个可执行文件的大小和 SHA-256。

内置 `en-US`/`zh-CN` 语言资源会打包进 EXE；用户还可以在 EXE 同级 `locales\` 目录放置自定义 JSON 语言包，无需重新编译。

公开仓库和 Release 发布前应确认工作树干净，且未跟踪用户工作目录或商业资源。`release\` 默认被 `.gitignore` 忽略。

EXE 不包含游戏资源、字体或 FFDec。用户仍需在 GUI 中选择自己的 PAK/CSV，并按适配器文档配置 FFDec。未配置代码签名证书时，Windows SmartScreen 可能显示“未知发布者”；发布者应在 Release 页面提供 SHA-256，并可在自己的 CI 中增加 Authenticode 签名步骤。
