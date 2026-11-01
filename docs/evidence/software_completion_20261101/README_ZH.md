# 2026-11-01 软件收尾：TreeDiagram

基线为 `d3d0fc1e94b8abc28f76a5f7aa95f26d2da0c2f8`。本次新增 CLI 的
`example --control-period-us`，用于明确创建 SCG 固定 10 ms 研究任务所需的场景；
默认仍为 20 ms，原数学核心导入保留。零、负或超界周期在写文件前拒绝，已有好文件不变。

SDK 的 32 个文件从 SilverStar 实际 exporter 取得，源码提交为
`ad2da03c3b248d15d7cf8e1c3278781fb7cd3f79`。新 PID/LQR 元数据记录显式的
每核心输出单位 1 N·m 映射和 ±1 N·m 研究范围，数学核心 C/H 与参数单位没有伪改。
SDK manifest 保留原始工作字节摘要；源 Git blob 与 Windows CRLF 的区别单独核对。

## 本次真实执行

| 执行 | 结果 | 证据 |
|---|---|---|
| Windows 完整 pytest | 118 passed，129.05 s，exit 0 | [完整日志](full-pytest-v1.log) |
| 全部示例矩阵 | 15 次真实运行，exit 0；原生/PID/LQR、四执行器、七估计器、Underline PID | [矩阵](examples-v1/matrix.json) |
| Underline 实际导出 → TreeDiagram import/check/run/export | 合成 200 N·s、61 个证据点、41 个仿真点；3 套 10 ms 参数包 | [运行与身份](cross-repository/actual-runs/results.json) |
| SCG 实际 CLI Preview/Apply → 正常生成 → `.ssdecoder` → C 消费者 | 三套全部成功，Preview 未改输入、Apply 原子提交，参数/单位/owner/实际输出逐项核对 | [接收结果](cross-repository/consumer/results.json) |

三套实际控制包为 PID、LQR、Underline 推力导入后的 PID。最后一套的 SCG 模型与 PID
模型逐字典相等；发动机推力改变 TreeDiagram 的物理输入，不会伪装成固件发动机驱动。
控制器仍 `deployable=false`，目标输出 `requested_body_y_torque_nm`，没有电气驱动。
上述 C 消费者使用实际生成源和 GCC `-fanalyzer` 编译链接；完整任务 ARM、资源与严格栈
另由 SilverStar 对最终构型验证，本表不将 Host 消费者当作 ARM 或硬件证明。

运行环境：Python 3.14.0 / Windows 11，NumPy 2.4.1，SciPy 1.16.3；完整命令、退出码、
source hash 与 SDK 对照在本目录保留。全部输入为合成 fixture，无台架或飞行精度结论。
Underline 的 Qt 生命周期缺陷已修复并独立验证：普通完整 383 passed，原失败集合与顺序的 381 项复跑也通过；实际推送提交为 [351ab0b](https://github.com/aleistercrowleybeast666/Underline_RETLDC/commit/351ab0b0167eb37bd6312c2bde79181d6225e97f)。motor 链路验证与该 GUI 回归分别记账，不互相替代。

```powershell
# TreeDiagram 仓库，已安装 requirements-tested.txt 与本项目
.\.venv\Scripts\python.exe run.py
.\.venv\Scripts\python.exe -m treediagram example research-pid.json --controller pid --control-period-us 10000
.\.venv\Scripts\python.exe -m treediagram run research-pid.json research-pid.tdrun.json
.\.venv\Scripts\python.exe -m treediagram export-parameters research-pid.tdrun.json research-pid.sstuning.json
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.test-tmp/software-completion-replay
.\.venv\Scripts\python.exe tools/verify_examples.py .qa/software-completion-replay --runs .qa/software-completion-replay-runs
```

SCG 接收端用 `python -m silverstar_fccg.project.tuning_bundle preview/apply`，显式选择
`--include-control-task`。本次跨仓库脚本在 SilverStar
`docs/evidence/software_completion_20261101/delivery/`；重放使用新输出目录，不覆盖证据。
实际运行目录与缓存分别位于 `.qa/software-completion-20261101/` 与
`.test-tmp/software-completion-20261101/`，未清理其他输出。

原模型边界继续有效：单级刚体、小攻角工程近似，非任意 SCG mission 等价；尚无六轴自动
控制分配、电气驱动、完整 ORK 等价、分离/柔性/回收伞或硬件资格。完整历史延期清单见
[首次交付报告](../../DELIVERY_20261101_ZH.md)。

功能提交 [997d112](https://github.com/aleistercrowleybeast666/TreeDiagram/commit/997d112c190ef1549ba5950f5e4f97c0a7c5ad8c) 已正常推送；[该提交的实际 push CI](https://github.com/aleistercrowleybeast666/TreeDiagram/actions/runs/41279773014) 通过。原始公开 API 收据见 [push-ci-v1.json](push-ci-v1.json)。
