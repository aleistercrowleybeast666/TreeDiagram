# TreeDiagram 开发约定

- 2026-11-01 用户明确将 SilverStar_Underline_TreeDiagram_Codex_Prompt_20261101.txt 作为完整实施任务：TreeDiagram 是独立六自由度仿真、装配、算法与参数交付桌面工具。此前仅 GUI 外壳范围已被本轮授权替代。
- 核心不得依赖 Qt；GUI/CLI 共用模型、校验与求解。仿真、宿主 C、生成固件、ARM 构建、硬件证据分别报告，未知不得伪装为已验证。
- GUI 调整遵循 `docs/GUI_STYLE_GUIDE.md`。跨仓库数据遵循唯一 owner：Underline motor 包、SilverStar 固件算法和参数、TreeDiagram 物理模型与结果。
- 函数使用名词_动宾、大驼峰，例如 `Project_Save`；Qt override 与 pytest 约定除外。公共成功/错误结果使用以 Result 结尾的 enum 和明确结果对象。核心层不导入 GUI。
- 保存先校验，再同目录临时文件 + 原子替换；保留上一版 `.bak`，拒绝版本不兼容、冲突、未知字段和损坏文件覆盖。失败不能替换当前工程状态或好文件。工程内容不写机器绝对路径。
- 优先使用现有 Python/PySide6，不复制别的仓库/虚拟环境。测试临时文件仅放本项目 `.test-tmp`，截图放 `.qa`；禁止生成巨大 `.work`、日志或样例。
- 文档保持紧凑；本轮保留必要契约、后端 ADR、测试证据与中文交付报告。
- GUI 修改做相关启动、导航、缩放、主题/字体、保存取消检查；持久化改动做相关故障测试。截图可辅助检查，不能代替测试。
- 清理仅可处理本项目已确认的临时输出，不清理用户工程、`.bak` 或未知文件。用户本轮明确授权正常推送至 TreeDiagram 指定远端，禁止 force push；不发布 release、不操作实物硬件。

