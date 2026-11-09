# GUI 收敛与本轮发动机包联调

本轮沿用 `b1157260ee4faa8a625b48530e48f0f0ef93e50c`，工作分支为
`codex/gui-convergence-20261110`。GUI 提交 `05d1c33`；最终受测实现提交
`6a571d0d9c635c176d7046276547a1bafba1e702`。主分支、产品版本、工程 schema、
交换合同与固定 SDK 没有因界面调整而改写。推送由三仓主负责人统一完成。

## 用户路径

概览现在显示实际模型、来源、缺项、历史结果和下一步。缺少质量等输入时不能运行；
模型页保留可定位问题，无缺项时收为一行。修复了从空工程加载完整模型后仍显示“先建立模型”的旧提示。
任务表把空间留给实现状态，结束阶段不再占据空白大列。

阶段胶囊打开实际摘要，并进入唯一共享算法与范围编辑器；修改影响全部引用阶段。
固定动力、滑行、下降阶段保持原含结束阶段语义，跨阶段不重建实例，退出范围 Stop。
PID/LQR 只显示所选算法的字段，另一算法草稿保留并受同次 Apply/Cancel 管理。
周期为整数微秒，输入小数保留草稿并报错；合法数值不按 Enter 可直接 Apply。
普通数值的空文本也不会再静默提交旧值，未编辑的高精度数值不会被显示精度舍入。

结果和比较选择按稳定 run ID 保留。空结果及无估计器运行分别说明导出条件；
参数说明区区分 INS/KF6 目标标量、PID/LQR 控制研究和尚无目标消费者的能力。
运行中编辑只影响下一版配置；关闭时等取消完成，再进入原未保存保护。
固定能力表移到帮助，真实 C 注册表与旧通用数学 demo 接口保持不同契约。

## 实际验证

Windows 11、Python 3.14.0、PySide6 6.10.1、NumPy 2.4.1、SciPy 1.16.3、
pytest 9.1.1、GCC 16.1.0。最终源码一次完整执行 **136 passed / 31.92 s**：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.test-tmp/gui-convergence-20261110/full-final
```

覆盖真实胶囊/共享编辑按钮、合法直接 Apply、空/小数草稿拒绝、Cancel/Esc、
保存重开、主题/导航、历史选择、旧 worker 不覆盖新配置、取消关闭和失败保留结果；
既有物理、C 算法、持久化、解析及 CLI 回归包含在同次完整执行。
此前 135/136 项阶段性结果不与最终结果相加。基线普通合法数值已能直接 Apply；
实际发现并修复的是空文本提交旧值，不把所有 `.value()` 调用泛称为错误。

Qt offscreen 在 920×620 逻辑尺寸、150% 深色检查了任务页和属性窗口；
主运行按钮位于窗口内，属性底部 Apply/Cancel 固定可达。不是原生桌面验收。
三仓主负责人另完成原生桌面验证：Windows 125% 下设置 `QT_SCALE_FACTOR=1.2`，
实测 DPR **1.5**，窗口 980×640 逻辑尺寸。实际打开 `CurrentAndHistorical.tdproj`、
点击结果页并导出参数，界面明确显示历史配置、18 s 达到时长、461.48 m 和当前消费范围。
原生导出的字节与下述 run 参数包完全相同，正常关闭没有未保存提示。
较早设置 `QT_SCALE_FACTOR=1.25` 的运行叠加系统缩放后实为 DPR 1.5625，不能称为 125%。
本应用仍仅有中文，未虚构英文支持；本轮没有另外证明实际 125% 桌面场景。
原生代表图由 SilverStar 正式证据唯一保存：
[历史结果截图](https://github.com/aleistercrowleybeast666/SilverStar/blob/18058cae6fbd2f861fc05081b9fed8a8b101d7be/docs/evidence/gui_convergence_20261110/gui_native/treediagram-result-150.png)，
[原生操作与范围](https://github.com/aleistercrowleybeast666/SilverStar/blob/18058cae6fbd2f861fc05081b9fed8a8b101d7be/docs/evidence/gui_convergence_20261110/GUI_NATIVE.md)。

实际构建 wheel，安装到独立包目录后用 `python -I` 验证导入来自该目录，
启动其 Qt GUI 并以新缓存执行真实 GCC 宿主编译。包内 **67 个源码/SDK 文件**
逐字节匹配受测源码；wheel 为 192473 B，SHA-256：
`e85b75d15c3f6805e0937fe9a8b05ab4b03976783f0d8fba458cb0c18a3c666c`。
这是 Python 包与现有依赖环境验证，不是新增独立 Windows EXE 或目标 ARM 验证。

## 本轮真实跨仓输入

输入为 Underline 本轮实际导入、处理、分析并导出的合成试验包，不是旧 golden 拷贝。
输入 SHA-256 为 `eed976bb0d95d90f680a6b72988e42b2a93b5342d5756a1d4a0a437930f017e3`，
总冲 225 N·s，推进剂 0.18 kg、总质量 0.42 kg、直径 0.054 m、长 0.24 m；
TreeDiagram 全程读取原件，前后哈希相同。

```powershell
.\.venv\Scripts\python.exe tools\verify_motor_delivery.py <new-motor.tdmotor.json> <new-output-directory>
```

脚本实际运行 CLI 导入/检查，以及 Qt 生产按钮的导入、后台仿真与参数导出；
测试替身仅选择文件和预览答案，不替代模型、校验器、科学计算、worker 或导出器。
它检查取消不变、同内容重导入、更新包保留本地安装/点火/质量模型、损坏摘要与未知版本
GUI/CLI 同样拒绝、缺干质量可预览但两端同样阻止运行，以及保存重开。

联调暴露了持久化后的 list 与 importer tuple 不同导致假“曲线变化”的真实缺口。
现按规范化声明内容比较，原曲线不变；新增 JSON 往返回归。
基线同包重导入误报 `time_s/thrust_n`，修复后 changes 为空，科学内容摘要相同。

实际完成 run `4008f769-9d31-4182-bee5-7477845b5870`，KF6 + PID / 10 ms，
输入 gravity 9.78、PID Kp 1.75；仿真 18.0 s、最高 461.4822213495483 m，
`landed=false`，明确为达到时长而非已落地或硬件验证。
运行后 GUI 改为 gravity 9.81，导出仍来自该完成 run 的 9.78；GUI/CLI 导出字节相同。
参数包 SHA-256：`ab27c43327d51c0c26988c26c3a2d5699c10ce7872592276d24750c95f6580b8`。

结果已迁到受保护的 `dist/gui-convergence-20261110/delivery/`，包括
`completed.tdrun.json`、`run.sstuning.json`、`CurrentAndHistorical.tdproj`。
正式精简证据见 [validation.json](evidence/gui_convergence_20261110/validation.json)、
[新链路 receipt](evidence/gui_convergence_20261110/motor-delivery.json)、
[重导入前后](evidence/gui_convergence_20261110/reimport-before-after.json)、
[安装包身份](evidence/gui_convergence_20261110/packaging.json)。
最终 wheel 位于 `dist/gui-convergence-20261110/`。迁移的14个文件共5,837,270字节，
逐件SHA-256完全一致；从迁移后的完成run重新执行CLI导出仍得到上面的同一摘要。
详见 [持久交付位置与复验](evidence/gui_convergence_20261110/durable-delivery.json)。
这些文件不再依赖pytest默认会清除的 `.test-tmp`；该交付目录有明确保护标记。

清理实际使用SilverStar已修复的同一清理API，预览、哈希清单、Apply后再重复执行：
移除180个缓存路径，逻辑内容2,425,121字节，重复执行移除0；515份源码、契约及交付输入
前后散列一致。D盘区间空闲量变化为-1,249,280字节，期间其他仓库归档写入，因此不把逻辑
删除量宣称为独占的物理回收量。详见 [清理回执](evidence/gui_convergence_20261110/cleanup/receipt.json)。
本轮没有删除仍有用途的SDK、validator、许可、Golden或用户工程。

## 范围与剩余项

本仓没有扩展任意任务图、气动理论、目标电气执行器或自动部署；研究记录保持
`deployable=false`。SCG Preview/Apply、生成消费者、目标资源/栈与硬件证据由其 owner
分别记录，不能用本轮仿真、参数导出或宿主 C 编译代替。
跨仓旧大证据归档及正常推送由主负责人统筹；三仓最终提交及推送状态见总交付报告。
