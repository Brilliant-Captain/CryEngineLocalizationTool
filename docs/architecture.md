# 架构

```text
CLI / GUI
 ├─ identify / pak / catalog / profile / workflow / apply
 ├─ core: models, profile, workflow, catalog, translation_table, stale, apply, manifest
 ├─ i18n: built-in and external JSON locale resources
 ├─ io: relaxed JSON, UTF-8 CSV
 └─ adapters: CryEngine, PAK, War of Rights, GFX/font, DDS
```

核心层只接受规范化路径和内存中的条目，不依赖具体游戏。`adapters.pak` 对 ZIP 风格 PAK 做路径安全检查、大小写折叠冲突检查和固定 ZIP 元数据写出；输出写入临时 partial 文件后通过原子替换完成。

文本流从 `scan_pak` 得到源路径，再由 `catalog_from_json_bytes` 生成稳定的 `resource_id`。翻译表的原文字段是只读校验依据，应用层只把非空且状态有效的译文写入深拷贝后的 JSON。状态层在原文哈希变化时清空旧译文并标记 `stale`，删除资源标记 `orphaned`。

外部工具通过参数传入并使用参数数组调用，不经过 shell。FFDec 的输出用于识别 DefineFont3 槽位；fontTools 默认由源码依赖或发布 EXE 内置调用，也可由用户传入自定义 Python 覆盖。DDS 默认使用标准库 PNG/PPM 解码和纯 Python DXT5 编码，Pillow 仅扩展其它图片格式。安装事务在进程检查、路径约束、哈希备份和原子复制后才写入；rollback record 会再次校验根目录，GUI 只能调用这些受保护接口。War of Rights 适配器支持显式 English-path overlay，manifest 记录加载策略；未声明 overlay 用途的重复路径仍被拒绝。
