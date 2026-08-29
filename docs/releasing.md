# 发布 Windows 独立 GUI

仓库不提交 `.exe`、PAK、GFX、DDS 或字体。推送版本标签后，GitHub Actions 会在 Windows runner 上构建 `CryEngineLocalization.exe`，上传构建 artifact，并把 EXE 与 `SHA256SUMS.json` 附加到对应 Release。

本地构建：

```powershell
python -m pip install -e ".[test,fonts,textures]"
python -m pip install -e ".[build]"
.\scripts\build_exe.ps1 -OutputDir .\release
```

输出目录包含：

- `CryEngineLocalization.exe`：one-file、windowed Tkinter GUI；启动后直接显示窗口，不打开控制台。
- `SHA256SUMS.json`：构建文件大小和 SHA-256。

EXE 不包含游戏资源、字体或 FFDec。用户仍需在 GUI 中选择自己的 PAK/CSV，并按适配器文档配置 FFDec。未配置代码签名证书时，Windows SmartScreen 可能显示“未知发布者”；发布者应在 Release 页面提供 SHA-256，并可在自己的 CI 中增加 Authenticode 签名步骤。
