# TreeDiagram 本轮交付（2026-11-17）

源码提交：[c97c753](https://github.com/aleistercrowleybeast666/TreeDiagram/commit/c97c753f76b84b8bdffffcdd0cd4f11c78b78853)。沿用 `codex/gui-convergence-20261110`，保留四工作区、离线仿真和既有算法能力。

未保存工程的关闭确认框按所属窗口居中，并限制在屏幕可用区域。取消不修改工程。SciPy 的 LQR 求解器改为实际执行 LQR 设计时装载，避免打开空工程时加载 LAPACK；求解公式、校验及结果快照语义保持原样。

全量 pytest **174 通过**；真实 Qt 150% 缩放居中/取消检查通过。新 wheel 在独立目录安装后，使用其 CLI 和 offscreen GUI 完成：新 Underline 包导入、取消/重复导入、坏版本/坏摘要拒绝、明确缺项阻断、一次完整后台仿真、历史结果标记、运行绑定参数导出、CLI/GUI 导出一致、工程保存重开。完整收据见 [wheel 联调](motor-delivery.json) 和 [打包收据](package-receipt.json)。

实际运行 ID：`b0797d0e-9229-4212-901d-3048ad8b53de`；合成试验输入总冲量约200 N·s，仿真18 s。实际导出参数 SHA256：`aec2e1b6d488c490f72f0956ffee0ceb942e8fdea5e7e4ac24272c38895a245b`。SilverStar 随后实际预览/取消/应用，并由生成的研究控制任务 C 消费，28个正常/故障场景通过；对应证据归档于 SilverStar 本轮报告。研究任务没有实物执行器输出。

交付目录：`D:\python_software\TreeDiagram\dist\platform_finish_20261117`。其中 wheel SHA256 为 `543cf3e6b04ffa663aa4c1e237a28511c21b58ec2e1492e4b37d8f2393a78489`，`validation` 保留本轮真实完成的合成输入、工程、运行结果与参数。

运行源码：`.venv\Scripts\treediagram.exe`。安装交付 wheel 后运行 `treediagram`。无界面流程可用 `treediagram-cli example model.json --controller pid --control-period-us 10000`，随后 `treediagram-cli run model.json result.tdrun.json` 和 `treediagram-cli export-parameters result.tdrun.json parameters.sstuning.json`。

未完成项：Computer Use 原生抓屏辅助进程阻断，本轮未完成原生桌面视觉复验；Qt offscreen 检查不能替代它。硬件待测：模型参数、控制输出及仿真精度的物理验证、硬件时序和飞行资格均未完成，也没有自动部署或实物驱动操作。旧发布包与历史证据保留，本轮临时文件仅使用 `.test-tmp`；正式交付已经迁到上述独立 `dist` 目录。
