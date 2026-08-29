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

外部工具通过参数传入并使用参数数组调用，不经过 shell。FFDec 的输出用于识别 DefineFont3 槽位；fontTools 只负责可选子集；Pillow/FFmpeg 只用于 DDS 探测，编码器不可用时返回明确错误。War of Rights 适配器封装语言键、English 路径冲突和配置备份规则，不能绕过核心安全检查。

