# 架构

```text
CLI
 ├─ identify / pak / catalog / apply
 ├─ core: models, catalog, translation_table, stale, apply, manifest
 ├─ io: relaxed JSON, UTF-8 CSV
 └─ adapters: CryEngine, PAK, War of Rights, GFX/font, DDS
```

核心层只接受规范化路径和内存中的条目，不依赖具体游戏。`adapters.pak` 对 ZIP 风格 PAK 做路径安全检查、大小写折叠冲突检查和固定 ZIP 元数据写出；输出写入临时 partial 文件后通过原子替换完成。

文本流从 `scan_pak` 得到源路径，再由 `catalog_from_json_bytes` 生成稳定的 `resource_id`。翻译表的原文字段是只读校验依据，应用层只把非空且状态有效的译文写入深拷贝后的 JSON。状态层在原文哈希变化时清空旧译文并标记 `stale`，删除资源标记 `orphaned`。

外部工具通过参数传入并使用参数数组调用，不经过 shell。FFDec 的输出用于识别 DefineFont3 槽位；fontTools 负责可选子集和覆盖率，缺失时诊断命令会指出替代解释器。DDS 默认使用标准库 PNG/PPM 解码和纯 Python DXT5 编码，Pillow 仅扩展其它图片格式。安装事务在进程检查、路径约束、哈希备份和原子复制后才写入；rollback record 会再次校验根目录，GUI 只能调用这些受保护接口。War of Rights 适配器封装语言键、English 路径冲突和配置备份规则，不能绕过核心安全检查。
