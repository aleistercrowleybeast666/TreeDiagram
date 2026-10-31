# SilverStar × Underline × TreeDiagram 实施交付记录

这是2026-11-01附件实施任务的实际结果记录。已建立能运行的三产品软件链，保留原有工作；下表区分已验证软件、有限模型、仍未证明的安全项和未执行硬件项。不是全部原始条目验收通过，也不是飞行资格或原版Power of Ten合规声明。

## 仓库、提交和固定依赖

| 仓库 | 起点 | 本轮代码/证据 | 推送状态 |
|---|---|---|---|
| SilverStar | feature/usb-transport-0.1.3-20261013，aaef99f82f0d33617ae82353b0ac760123d56cc0；已有327项dirty/untracked | 4f701b4a7822302dc0f4ac858549f7cc7fa4ba0e主体代码；a5be57c控制v1证据；10e1eb3真实跨仓库v2证据；后续GUI/H7收尾另列 | 保持当前分支，本轮未推送 |
| Underline_RETLDC | main，f913c376daf9cb7ebedfd584069866fe510aa30c | 153fbd6主体、e4001bf730692f58071a1df4d1efad756bd84379受测代码、c1f8ac76f9bbcde1076ef9e48624c920ad161960最终证据/字节pin | 本地3个提交；远端main核对仍f913c376 |
| TreeDiagram | 现有GUI目录无Git，远端空 | fa6d2e2保留原GUI；1983911首批工作台；440db63执行机构和来源修复；81349fc27690374b617d18c3a52690807010c1cb图例排版；后续证据提交另核对 | 正常main推送，最终SHA见交付消息/远端ref核验 |

原有SilverStar AGENTS/root库存清单/旧证据归档保留，没有混进本轮代码提交；Underline原未跟踪showcase review保留。未删除旧.work、原始记录、SDK、用户CubeMX输入或冻结release。

TreeDiagram只包含小型数学SDK与声明契约，不复制整个SCG/GSHC/Underline。SDK来源固定4f701b4，逐文件字节hash与许可证在algorithms/sdk/manifest.json；工作字节记录本身是权威，source_commit不替代它。motor合同固定Underline e4001bf，schema SHA `23b484e42ed2245c2547562969ade6327222c46eaf83954dcffdd6750f3ce3d2`，validator SHA `ea4eaaf4e38587e44678a3bd05fef476fda2329c49596ce7201cbbbba0479988`。Git提交原始字节也已逐项校验，避免Windows换行造成pin漂移。

## 普通用户可走通的入口

1. Underline按原界面导入、标定/极性/补偿、划定试验区间，在既有导出框选择TreeDiagram格式。导出科学快照与来源，原GUI布局/主题/导航保留。也可headless处理已保存工程。
2. TreeDiagram打开离线装配示例或ORK支持子集，导入`.tdmotor.json`，补充明确质量/惯量/气动与安装，设置一次算法和阶段范围，运行真实6DoF。
3. 查看真实轨迹/姿态、位置速度、估计误差、请求/实际响应、事件/诊断；旧结果绑定旧快照。导出`.sstuning.json`。
4. SCG任务页导入参数包，Preview一次、Apply一次；研究控制核心要显式附加生成。生成参数进入实际C配置访问器和完整decoder，不能把导入成功视作实机READY。

## 要求到实现/验证的映射

| 附件范围 | 实际实现与入口/owner | 状态与证据 |
|---|---|---|
| 0–3 基线/边界/单后端 | 三repo核对；TD physics/simulation与ADR；固定SDK/contracts | 已实现；参考项目不作为强制依赖，MAPLEAF本机执行未完成 |
| 4 SCG三页/唯一实例/共享无线 | SCG ui工作流、radio_transaction、单owner属性、参数Preview/Apply | 已实现并持续完整GUI回归；offscreen截图会单列，不冒充桌面硬件 |
| 5–8 mission/S/START/NRF/SX1278 | SilverStar现有10/27工作保留并集成，owning模板/插件与正常生成入口 | 当前fresh构型/Host/ARM结果以SilverStar正式矩阵为准；不把历史通过移植给新二进制 |
| 9 GSHC事件/寻回 | 当前SS-TM-S接收、会话/缓存/队列等来源实现 | 全套带实际当前C DLL执行；失败环境及重试保留 |
| 10–11 安装标定/GNSS | 真实维护owner、采集/候选/Apply/保存/读回和GNSS原后端 | 软件路径和Host回归有证据；production-qualified IMU/MAG仍为0，真实Airborne<4g读回/上板链未测 |
| 12 FLP/decoder | 精确ssdecoder路径，修复重复候选搜索set打乱优先根 | 5完整文件75/75、额外4合同文件37/37；没有fallback解码 |
| 13–15 资源/栈/真实入口 | 新生成的ELF/源图/分bank资源/Power10/Analyzer | 各构型单独报告；严格stack FAIL/critical-contract NOT PROVEN保留，不能由RAM余量宣称栈安全 |
| 16 Underline原生包 | ExportSnapshot、ProjectPipeline、原ExporterPlugin和CLI，owner schema/validator | 完整379通过，桥接31通过，中英/明暗offscreen；来源/CWD真实缺陷复现后修复 |
| 17.2 模型与ORK | design/geometry/importers/workbench；稳定ID与自身质量/父变换 | 原生装配可运行；ORK常见单级结构子集；未知关键字段/缺项阻断，不宣称全格式物理等价 |
| 17.3–5 物理/调度/执行机构 | 单RK4，整数微秒、步内事件、环境/相对风/变量质量/四机构 | 解析/守恒/收敛/事件/延迟测试与15场景矩阵；物理近似边界见CONTRACTS |
| 17.6–7 真C算法 | sdk固定数学代码+每运行独立context、实际PID/LQR | 七估计器均有实际输出与结果码；52算法专项；未把Python近似称同核 |
| 17.8 参数闭环 | 原严格profile +独立control-research +外层bundle，SCG owner | v3三实际run束143/143标量，完整decoder与真实编译消费者一致；电气驱动/任务调度尚未接通 |
| 17.9 GUI | 模型/算法/结果；原子草稿/后台取消/快照 | 实际Windows桌面打开、Esc/Apply、运行/取消、结果与导出、错误导入；100/125/150离屏截图 |
| 18–19 复现/提交/报告 | examples、CLI、测试、wheel、固定合同、原始日志/哈希 | 原生、四机构、七估计器、Underline链和ORK正负例齐备；最终推送ref另核对 |

## 本轮数值结果与算法边界

这些数值来自`evidence/20261101/final-examples-v2/matrix.json`对应的实际运行，不是预测硬件性能。

| 场景 | 最大高度m | 停止时间s | 状态/冲量 |
|---|---:|---:|---|
| 原生无控制 | 117.1244056 | 10.860796 | 落地，109.875Ns |
| 原生KF6+PID | 117.1776958 | 10.865561 | 落地，109.875Ns |
| 原生KF6+LQR | 117.2494491 | 10.866709 | 落地，109.875Ns |
| Underline合成试车+PID | 382.9825722 | 18.0 | 到配置时长，尚未落地，200.00000000000003Ns |

| 算法 | 源码/Host/数值 | 本轮生成/ARM | 硬件 |
|---|---|---|---|
| INS/SF6/KF6 | 原C、真实执行、固定输入/plant验证；KF6/SF6姿态明确来自INS | 既有插件；按实际F407/H743配置报告，未把每个Host算法都宣称独立全ARM构型验收 | 未测 |
| ESKF15 | 原C预测/量测、Body子样、正确右乘误差、同时间输入 | 既有插件；独立实验gate保持，不宣称全部策略通过 | 未测 |
| ESKF20/InEKF15/InEKF20 | 原fp64 augmented核，显式先验、strict co-timed；倾斜初值宿主矩阵精度已修 | H743现有真实后端保留；其他完整构型以矩阵为准 | 未测 |
| PID/LQR | 新SilverStar C内核，两端同核；PID饱和/恢复，LQR DARE/float32 K/实际限制 | 两套正常F407完整ARM/architecture/power10/analyzer/artifact通过；两套严格stack均失败 | 未接电气驱动，未测 |

四类执行器是Python物理plant，均有实际受限响应：gimbal连接发动机推力、fin连接动压、wheel内部角动量、rcs推力对与资源消耗。它们不是四个C控制律，也没有相应硬件驱动。固定显式分配仅Body Y单轴，其余自由度欠驱动不补理想矩。轮饱和按步内到界时间一致交换，冷气耗尽用有界二分定位并停止剩余推力；同组真实Plant测试旧代码5失败→新代码5通过，完整物理22通过。

阶段是固定powered/coast/descent的仿真子集，inclusive结束范围、连续状态保留。尚未接任意SCG mission图、一次性功能生命周期、全套机载对准/校准、source/generation切换、历史重放/recovery编排；增强核非零延迟量测真实返回Stale。不是菜单里选到就意味着机载全功能接入。

## 安装与复现

TD运行完整命令见根README；`requirements-tested.txt`锁定本轮直接依赖，GCC需本机已有或通过CC指定。真实wheel已构建，隔离Python从wheel安装目录导入并执行C内核，逐文件与源码匹配。没有承诺新Windows安装器或全新OS环境已验收。

```powershell
# TreeDiagram根目录
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-tested.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe run.py
.\.venv\Scripts\python.exe -m treediagram run examples/underline-pid.json run.tdrun.json
.\.venv\Scripts\python.exe -m treediagram export-parameters run.tdrun.json run.sstuning.json

# Underline根目录，原应用环境
.\.venv\Scripts\python.exe -m underline_retldc.cli export tests/fixtures/motor_test_package/v1/synthetic_positive.retldc.json motor.tdmotor.json
```

SCG无GUI采纳示例及正常生成命令保存在其`docs/evidence/treediagram_algorithms_20261101/v3/validate_actual_runs.py`与README；使用TD受测解释器以匹配算法实现身份。输入导出→Preview→Apply→保存重开→正常生成→decoder校验→真实C消费者逐位比较，不是只读JSON。

GUI截图与失败历史：[TD验证索引](evidence/20261101/README.md)。Underlineside完整报告的保留副本：[桥接验证](evidence/20261101/cross-repository/underline-validation.md)。本地SilverStar正式矩阵位于`D:/python_software/SilverStar/docs/evidence/treediagram_20261101`；控制v1/v2/v3证据在相邻`treediagram_algorithms_20261101`。本轮未推送这两个仓库，不能把这些本地新提交写成远端已可访问链接。

## 准确未完成项和延期

- **安全验收未完成**：全程序调用图/间接调用、所有任务及MSP/ISR嵌套/动态帧/栈余量与WCET完整证明；严格stack拒绝过期callback依赖hash。Power10文本工具通过也明确critical-contract NOT PROVEN。没有扩大允许表。
- **H743存储软件问题继续处理中**：导入CubeMX SD owner有blocking API与无界ready等待、回调handle过滤不足；不能修改用户输入或用F407胶水直接替换。后续受控H7 owner评估/实现结果另记，不先宣称修复。
- **硬件/外部资格缺失**：实际安装标定全链上板、生产IMU/MAG资格、GNSS Airborne配置读回、无线TX_DONE/最长空窗压力、USB枚举/断连压力、完整栈high-water与MCU WCET、真实飞行/台架准确性。合成fixture不是硬件证据。
- **明确软件能力边界**：TD工程气动与均匀燃料/单级刚体模型；无分离、回收伞、晃动/柔性、完整ORK等价、气动表入口、六轴自动控制分配；全部固件参数/对准/重放未绑定到Host；执行机构目标电气驱动和任务调度未接。参数导出research-only且deployable=false。
- **Underline范围**：第一版原生包完整推力和motor metadata，压力/温度辅助流未接；未制作新EXE；未知或历史未保存的资格不伪造。
- **用户明确延期**：活动H半双工重新设计、飞行中无线在线调参、运行时XYZ杆臂补偿。本轮仍S，XYZ为预配置/元数据，软件模拟安装不等于固件补偿。
- **验证范围缺项**：其他OS桌面、独立安装器、MAPLEAF标准构建已实际失败（Cython/pkg_resources环境兼容），其仿真与ActiveRocketPy本机执行、全依赖商业捆绑再分发审查未执行。已有日志和脚本的准确范围不外推。

临时输出在各任务版本目录，保留owner/用途/证据hash清单；未执行任务末清理。权限问题没有被绕过，旧.work少数目录读取拒绝已跳过。最终报告补充具体新结果后才结束本轮。

