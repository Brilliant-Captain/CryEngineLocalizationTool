# GUI 界面本地化

CryEngine Localization 的界面文字由 JSON 语言资源驱动。默认界面是简体中文（`zh-CN`），英文（`en-US`）是回退语言。新增语言不需要修改 Python 代码。

## 新增一种语言

1. 复制项目中的 `src/cryengine_localization/locales/en-US.json`。
2. 将文件名改为目标 locale，例如 `ja-JP.json`。
3. 保留 `locale` 字段与文件名一致，翻译 `name` 和 `strings` 中的值。
4. 不要修改 `strings` 的 key，不要删除 `{path}`、`{count}`、`{message}` 等格式占位符。
5. 运行 GUI，在顶部的“界面语言”下拉框选择新语言。

开发者可以把文件提交到 `src/cryengine_localization/locales/`，重新打包后成为内置语言。普通用户不需要重新构建：把 JSON 放到 EXE 同级的 `locales/` 目录即可：

```text
CryEngineLocalization.exe
cry-localize.exe
locales/
  ja-JP.json
```

也可以设置外部目录：

```powershell
$env:CRYENGINE_LOCALE_DIR = 'D:\MyCryEngineLocales'
.\release\CryEngineLocalization.exe
```

外部资源优先于内置资源，适合个人修改或测试。资源格式必须是：

```json
{
  "locale": "ja-JP",
  "name": "日本語",
  "strings": {
    "app.title": "CryEngine Localization",
    "button.save": "保存"
  }
}
```

只提供部分 key 也可以：缺少的 key 会先从 `en-US` 取值，英文也没有时直接显示 key，避免界面出现空白。新版本新增的批量扫描、摘要预演、旧译文复用、翻译/字体独立打包等按钮也遵循同一回退规则；维护外部语言包时只需从最新版 `en-US.json` 补充想本地化的 key。

## 选择和保存语言

- GUI 顶部下拉框可即时切换语言，当前表单值不会丢失。
- 保存 project profile 时，界面语言写入 `ui_language`；目标游戏语言仍由 `language` 字段控制，两者互不影响。
- 旧 profile 没有 `ui_language` 时自动使用 `zh-CN`。
- CLI 启动 GUI 时可显式指定：

```powershell
cry-localize gui --ui-language zh-CN
cry-localize gui --ui-language en-US
```

CLI 的 JSON、错误和数据输出保持原有格式，不会因为 GUI 语言切换而改变，便于脚本解析。

## 翻译原则

- key 是程序接口，不翻译、不改名。
- 保留格式化占位符及其拼写；如果源文本含有 `{path}`，译文也必须含有 `{path}`。
- 文件使用 UTF-8 编码，JSON 必须是对象，`strings` 的 key/value 都必须是字符串。
- 提交新语言时，建议同时运行 `python -m pytest -q`，并在 GUI 中检查主要页签和确认框。
