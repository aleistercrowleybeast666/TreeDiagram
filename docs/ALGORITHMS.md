# 实际 C 算法与参数边界

TreeDiagram 直接编译 `src/treediagram/algorithms/sdk/` 中固定的 SilverStar 数学源码。
`manifest.json` 逐文件记录原仓库路径、SHA-256 和来源提交；它明确标注工作区内容快照，
不是宣称所有文件都来自该提交的干净树。SDK 不含 HAL、RTOS 或伪造的设备接口。
旁边的 `native/` 是显式宿主适配。每个运行持有独立 C context/workspace，无共享可变全局状态。

首次使用要求 GCC（可用环境变量 `CC` 指定），仅本地编译，不联网下载、不加载工程文件指定的代码。
缓存及运行实现身份包括源文件清单、内容、宿主配置、C 适配代码、Python 导航/控制包装源码、
Python/NumPy/SciPy 实际版本、编译器版本和编译选项；改变输入不会复用旧身份。
`build.json` 同时保存这些数值运行环境和包装源码摘要，历史运行重新导出会检查身份一致性。
缓存默认位于用户 `.cache/treediagram/algorithms`，可用 `TREEDIAGRAM_CACHE` 改到指定目录。
失败会报告实际编译日志，没有伪装成 C 实现的 Python 回退。

| 实现 | 固定源码版本 | 宿主能力及边界 |
|---|---|---|
| Coning2Sculling2 INS | 0.1.0 | 真实二子样 C 预积分和姿态传播；首个完整区间前 Waiting |
| SF6 | 0.2.0 / revision 2 | 真实固定增益估计；无协方差、NIS、历史回放；量测和接收时刻须严格递增 |
| KF6 | 0.4.0 / numerical revision 1 | 真实 C 六维位置/速度；INS 单独提供姿态；当前状态到达时更新，保留原量测年龄；此桥接不执行历史重放或固件 GNSS 恢复编排 |
| ESKF15 | 0.4.0 / update numerical revision 2 | 原始 Body 子样、右乘姿态误差；实际 C 预测和量测；此桥接仅接纳同时刻 GNSS |
| ESKF20 / InEKF15 / InEKF20 | augmented.common 0.3.0 | 真实双精度 C bounded 内核；显式先验、共点、严格同时刻 GNSS；20维核支持真实磁量测，15维 InEKF 不提供磁量测 |
| PID | 新 0.1.0 | 同一 SilverStar C 内核；微分作用于测量，低通、积分/输出限幅和条件积分 anti-windup |
| LQR | 新 0.1.0 | 离线 SciPy DARE，目标 float32 K，再由同一 C 核执行 2 状态/1 输入反馈和限幅 |

这些是数学内核接入状态，不能等同所有机载 backend、对准、标定、延迟重放、传感器质量处理或硬件验收。
SF6/KF6/ESKF15 提供实际气压高度更新；20维增强核提供实际磁量测更新。
磁量测保留传感器轴系，安装旋转在宿主初始化显式传入，只组合一次；
输入单位 T 转原核心 uT，标准差平方一次得到 uT²。模拟校正资格明确是 simulated，
不是实际硬件校准资格。增强核不接纳过时磁量测，非零延迟下会报告 Stale；
尚未接入原固件 replay/session 编排。算法没有某项量测时返回 Unsupported。

默认初值为用户配置的发射架姿态、发射点零位置和零速度，是明确的仿真假设。
模拟 IMU 输入为机体比力 m/s² 与角速度 rad/s；ENU，Hamilton wxyz，`q_nb` 为 Body→Navigation。
初始化之后，估计接口没有真值姿态输入。0–1 s 常加速度与定角速度用例验证重力符号、位置/速度和旋转方向。
只在输入时刻合法、实际更新成功时发布更新；延迟/重复/未来输入不会被改写成有效当前量测。
增强核由整数微秒端点计算每一步 double 时间差，防止浮点累加使本来同时刻的量测失配。

宿主 KF6 固定编译配置来自仓库 `navigation_perf_config/system_user_config.h`，INS 采用二子样聚合；
固件所有参数的全量可编辑性并不等于宿主桥接已开放同样参数。
ESKF15 的先验对角线为位置/速度 1、其余 0.01（对应各误差坐标平方单位），
噪声幅度密度分别 gyro=0.001、accel=0.05、gyro-bias RW=0.00001、accel-bias RW=0.001，
这些是仿真参考配置而非传感器校准证书。增强核显式 covariance diagonal=0.1，
gyro/accel 幅度密度=0.001/0.05，bias RW=0.00001，安装初值为同点单位旋转；
ESKF20 按原核要求交换 accel/gyro 密度顺序。显式默认磁场参考 ENU 为 (20,0,-40) uT，
磁倾角/偏角从这份环境配置计算，不能由真值姿态反推。
离散测量标准差与幅度密度不混用，GNSS 标准差只平方一次。

PID 使用 `error = reference - measurement`；默认场景输入为俯仰角 rad，输出为请求 Body Y 力矩 Nm，
因此 kp、ki、kd 的单位依次为 Nm/rad、Nm/(rad·s)、Nm·s/rad。
进入持续范围后状态保持；Stop 清空积分与微分历史，Reset 才重新开始；非法周期/非有限输入不给出有效输出。
宿主的失败处理抛出 `ControlError`，C 接口将输出清零；内部状态损坏/溢出会停止该实例。
积分限幅发生前检查溢出，不通过浮点 min/max 把无穷值隐藏成正常饱和。

LQR 首版状态为 `[angle_error_rad, angular_rate_radps]`，输入为 `actuator_command`。
默认演示明确把该命令解释为请求 Body Y 力矩 Nm，B 由参考惯量与 1 Nm 单位权限离散化；
不能把同一 K 不经建模转换成归一化舵角或另一个轴。
模型是固定参考惯量、小扰动、单轴刚体。真实执行器限幅、滞后、低动压及燃尽由 plant 单独执行。
线性稳定性不是全飞行包线稳定性证明。

DARE 验证 Q 对称半正定（不是一律要求正定）、R 正定、PBH 可稳定/可检测条件、求解残差，
并重新验证量化到 float32 的 K 的闭环谱半径。真实 C 限幅闭环另有数值回归。
算法参考：[SciPy solve_discrete_are](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.solve_discrete_are.html)。
本轮实际运行依赖版本以项目验证报告为准，不把在线最新文档版本当成本机版本。

## 参数交付

`silverstar.tuning-bundle/1` 的唯一语义 owner 是 SilverStar 的
`contracts/tuning_bundle_v1.schema.json` 与 `project/tuning_bundle.py`。
TreeDiagram 携带固定 schema 副本，旧 `silverstar.function-parameters/1` 的字段与上限不变。
`*.sstuning.json` 内含：模型摘要、run ID、实际实现身份、旧严格 scalar profiles、独立控制研究记录和限制。
控制记录矩阵固定 2×2/2×1/1×2，row-major，包含 A/B/Q/R、实际 float32 K、dt、状态/输入顺序与求解诊断。
`content_sha256` 是排除该字段后，UTF-8、sort_keys、紧凑分隔、禁止 NaN 的 JSON SHA-256。

当前只有 INS/KF6 导出对应目标标量 profile：固定目标默认配置加本次真实仿真使用的 gravity 绑定。
这些是待检查的目标输入，不宣称所有机载后端参数已由当前宿主运行验证。
旧只读参数保留其原始保存值；单位、身份、未知字段、冲突共享参数、布尔伪数值与非法摘要会被 SCG 拒绝。
多 owner 完整校验后一次提交，取消/失败不改原模型。

SCG 的显式 `--include-control-core` 可把独立研究控制参数映射到新插件 owner：
正常生成源图包含 `control_pid/lqr.c` 和 `control_*_project.c`，
`ControlPid_ProjectConfigGet` / `ControlLqr_ProjectConfigGet` 真实消费当次生成的 float32 参数。
这是只包含数学核心的构建接口，不会自动启用任务调度。
本次软件收尾的 SCG 另提供显式 `--include-control-task`：把一个 PID/LQR 实例接入既有
FlightTask 的固定 10 ms 研究调度，并沿真实阶段范围保持状态、在停止或故障后撤销输出。
GUI 在参数预览中提供同一可选项，默认不选；周期不匹配时不能启用，原数学核心导入仍可用。
此接口读取有来源、采集轮次和标定版本的有效导航/IMU 数据，输出是有界研究快照，
没有连接执行器电气驱动；`deployable=false` 保持不变。TreeDiagram 的四类执行器模型仍是仿真模型。
目标适配器目前限定 Body Y 小角度平面运动，明确采用每个数学核心输出单位对应 1 Nm 的参考映射；
研究快照的 `requested_body_y_torque_nm` 表示请求力矩，当前限幅不超过 ±1 Nm。
这与 TreeDiagram 仿真中的力矩单位一致，不能当作任何实际舵机或发动机的标定。
普通导入只应用匹配且已选择的 INS/KF6 profile，不能凭导入授予 READY。

```powershell
# TreeDiagram checkout, no GUI required
python -m pytest tests/test_algorithms.py --basetemp=.test-tmp/algorithm-tests -q
python -m treediagram example research-pid.json --controller pid --control-period-us 10000
python -m treediagram run research-pid.json research-pid.tdrun.json
python -m treediagram export-parameters research-pid.tdrun.json research-pid.sstuning.json
# SilverStar checkout
python -m silverstar_fccg.project.tuning_bundle preview project.ssproject run.sstuning.json
python -m silverstar_fccg.project.tuning_bundle apply project.ssproject run.sstuning.json --output tuned.ssproject --include-control-core
# Explicit research task opt-in; requires a compatible 10 ms control record
python -m silverstar_fccg.project.tuning_bundle apply project.ssproject run.sstuning.json --output research-task.ssproject --include-control-task
```

SilverStar 普通 GUI 也提供 bundle Preview/Apply。`tests/fixtures/algorithms/` 保存实际 C 轨迹导出的
PID/LQR golden bundle、导出时源码清单与宿主适配文件哈希；它们是合成数学证据，不是硬件日志。
源 SDK 可从 SilverStar 用 `apps/SCG/tools/export_algorithm_sdk.py <destination>` 明确重新导出。
