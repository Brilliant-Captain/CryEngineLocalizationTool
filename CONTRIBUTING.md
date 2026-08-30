# Contributing

感谢贡献 CryEngine Localization。项目面向通用 CryEngine 项目，GUI 和 CLI 共用同一套核心逻辑。

## 开发环境

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test,fonts,textures,build]"
.\.venv\Scripts\python.exe -m pytest -q
~~~

提交前请运行：

~~~powershell
python -m compileall -q src scripts
python -m pytest -q
git diff --check
~~~

## 代码约定

- 核心逻辑放在 `core`、`io` 或 `adapters`，GUI 只编排用户操作，不绕过安全接口。
- 新增文件操作必须保留源文件、使用路径约束，并在失败时不留下伪成品。
- 外部程序使用参数数组调用，不拼接 shell 命令。
- 新功能先写合成 fixture 测试；不要在测试中依赖商业游戏资源。
- CLI 输出保持稳定；GUI 文案必须使用 `src/cryengine_localization/locales/*.json` 的 key。

## 新增界面语言

复制 `src/cryengine_localization/locales/en-US.json`，改名为 `<locale>.json`，只翻译 `name` 和 `strings` 的值。不要修改 key、格式化占位符或 JSON 结构。新增语言应补充 i18n 测试，并在 GUI 中检查主要页签和确认框。

## 不要提交的内容

- 商业游戏 PAK、解包目录、GFX、DDS、字体、EXE、DLL、JAR 或安装包
- 真实游戏路径、玩家用户名、临时目录或安装记录
- FFDec 或其他外部工具的二进制文件
- 真实翻译 CSV、备份文件和生成的 manifest

合成的很小测试文件可以提交，但必须不包含商业资源和个人路径。

## Pull request

Pull request 请说明：

1. 变更目的和影响范围。
2. 新增/修改的测试及运行结果。
3. 是否修改了 GUI、profile schema 或 CLI 参数。
4. 是否需要手动验证外部工具或真实 CryEngine 项目。
