# ADR 001 — 一个可测试的离线物理后端

决定日期：2026-11-01。采用 TreeDiagram 原创紧凑 RK4 刚体后端 `treediagram.rk4/1`。数学状态与 GUI 分离，整数微秒调度在每个传感器采样、到达、控制、输出与发动机折点分段；连续事件在步内二分定位。一个求解器同时服务 CLI 和 GUI，避免双实现漂移。

选择理由是这次需要在明确边界处调用固定 C 估计器与控制器、检查传感器因果、保留实际拒绝结果、独立测试力/矩和执行机构。先实现可审阅的有限物理范围；没有证据表明其准确性优于成熟模拟器。当前只有规定推力、冲量比例均匀圆柱燃料、刚体、局部平地、ISA 对流层和小攻角亚声速工程气动。不实现柔性、燃烧室、晃动、分级碰撞、回收伞、自动全包线控制。

## 实际参考

以下为本轮 `git ls-remote ... HEAD` 返回的身份；只读公开文档/源码说明，没有导入其代码。API 与许可判断只适用于所查看版本。

| 参考 | 观测 HEAD | 用途与取舍 |
|---|---|---|
| [RocketPy](https://github.com/RocketPy-Team/RocketPy) | 9bd6ad3af8f97bafa3201d4e70eba2877e66e040 | 官方 1.13.0 文档包含6DoF和传感器/控制扩展；学习模型分层，未采用为依赖，未声称无控制能力 |
| [MAPLEAF](https://github.com/henrystoldt/MAPLEAF) | af970d3e8200832f5e70d537b15ad38dd74fa551 | 学习六自由度模块组织；GitHub API最后5条默认分支提交截至2021-12-11，repository pushed_at=2023-12-27，archived=false；本机实际固定源码构建两次失败，见下文，未运行其仿真 |
| [AeroVECTOR](https://github.com/GuidodiPasquo/AeroVECTOR) | 566bdeb035132fe18ce66dbdb22180d03b744fc4 | 其公开核心为3DoF；只参考执行机构/配置组织，不用来充当6DoF |
| [ActiveRocketPy](https://github.com/ARRC-Rocket/ActiveRocketPy) | 3b3d6c02feafab8e0ef29908c75a8190a6cdc268 | 参考控制插入思路，未依赖fork私有API或引入代码；接口本地兼容性未验证 |
| [OpenRocket](https://github.com/openrocket/openrocket) | 4b4b387a9d822114515aa578a185b87bfebfbc24 | 对象树、属性与公开ORK规范；导入结构子集不代表物理等价 |
| [RocketSerializer](https://github.com/RocketPy-Team/RocketSerializer) | 66d8ca8c9be36816c4157fbdf249e87fb8c1f5dc | 参考模型转换缺项边界；没有作为运行依赖 |
| [JSBSim](https://github.com/JSBSim-Team/jsbsim) | 911b2d48ce934da183556983ec60b2069faa46fb | 参考力/矩及轴系模块边界，未建设第二后端 |

[OpenRocket 文件规范](https://openrocket.readthedocs.io/en/latest/dev_guide/file_specification.html)、[RocketPy 官方文档](https://docs.rocketpy.org/en/latest/)和 [SciPy DARE](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.solve_discrete_are.html)是具体接口参考。没有执行其他模拟器的精度对照；“参考”不表示已复现其示例或确认fork可运行性。

MAPLEAF本地可行性做了限定的真实构建检查：Windows/Python3.14.0/pip25.2，从上述固定Git提交URL运行`pip wheel --no-deps --no-cache-dir`，未引入产品依赖或修改外部源码。第一次`--no-build-isolation`因当前环境没有Cython而退出1；第二次使用其标准隔离构建，在执行setup.py导入`pkg_resources`时退出1。完整输出为`evidence/20261101/mapleaf-build-probe.log`和`mapleaf-build-isolated.log`，均有退出码文件。其当前声明还固定matplotlib3.2.2；未为本轮另建旧Python/旧依赖平台。结论仅为本次安装路径未成功，不能推广为MAPLEAF无法运行；未获得其仿真或交叉精度证据。ActiveRocketPy本机兼容性仍未执行。这不阻断已选后端。

## 验证与后果

解析无力/恒力/恒矩、自由转动能量/角动量、动量轮反作用、相对风、变量质量、步长收敛、离轨/顶点/落地和传感器延迟是当前物理验证。真实 C 内核另外验证。默认示例离线可运行。未来新增气动表、六轴分配、回收模型应增加版本化输入和同核心验证，不建立独立GUI求解实现。
