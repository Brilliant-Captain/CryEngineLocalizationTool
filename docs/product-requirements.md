# 产品需求

## 目标

为 CryEngine 项目提供一个安全的本地化工作流：从 PAK 中建立文本目录，维护原文与译文，识别游戏更新造成的失效条目，并生成可回滚的补丁包。

## 非目标

- 不携带或分发商业游戏资源、用户字体和 FFDec 反编译产物。
- 不支持 Unreal Engine 或其它引擎。
- 不保证任意版本的 Scaleform/GFX 都能由同一套外部工具修改；工具失败必须显式报告。

## 功能要求

1. 识别 CryEngine 项目并报告置信度和引擎版本线索。
2. 只读扫描、提取和确定性重打包 ZIP 风格 PAK。
3. 从 CryEngine JSON（包括尾逗号格式）提取文本到 UTF-8 CSV。
4. CSV 独立保存 `original_text`、`original_hash` 和 `translation`；导入不能篡改原文字段。
5. 根据资源路径、文本键和原文哈希标记 `active/new/stale/orphaned/invalid`。
6. dry-run 输出将修改的资源、键和译文，不写入源包或游戏目录。
7. War of Rights 适配器默认拒绝重复 `Localization/english/` 路径，支持语言配置预览、备份和恢复。
8. GFX 字体槽位动态发现，支持全量字体和 fontTools 子集命令；DDS 替换校验尺寸、MIP、压缩格式和 Alpha。
9. 构建输出包含 manifest、源包哈希、替换项、字体方案和构建时间；失败不生成最终成品。

## 验收标准

所有核心逻辑有合成 fixture 单元/集成测试；真实游戏资源只作为本地手工输入。仓库扫描不得发现 PAK、GFX、DDS、字体、临时输出或用户绝对路径。

