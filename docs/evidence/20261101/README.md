# TreeDiagram 2026-11-01 验证记录

初次完整代码提交：1983911f419190e80241a4ed851462516a1de737。`source-snapshot.json`保留当时110个源码/fixture/配置工作字节SHA及环境。后续440db63修复执行机构饱和/耗尽、加强motor数据验证并增加来源查看；81349fc仅修正图例单位文字重叠。最新工作字节与依赖见`source-snapshot-81349fc.json`，固定C快照仍为4f701b4a7822302dc0f4ac858549f7cc7fa4ba0e。提交名本身不替代字节身份；记录脚本和说明后续变化不冒充新的运行结果。

## 最终增量验证

| 实际命令/范围 | 证据 | 结果 |
|---|---|---|
| `.venv/Scripts/python.exe -m pytest -q --basetemp=.test-tmp/actuator-full-20261101`，440db63业务源码 | pytest-actuator-final.log / .exit.txt | **113 passed，56.48s，exit 0** |
| `tools/verify_examples.py docs/evidence/20261101/final-examples-v2 --runs .qa/20261101/final-runs-v2` | examples-actuator-final.log、final-examples-v2/matrix.json | **15实际场景，exit 0**；包含最新轮/RCS实现及来源假设 |
| 81349fc文字排版后的完整workbench测试文件 | pytest-motor-label.log | 5 passed，2.83s |
| 81349fc wheel构建、独立目录安装、`python -I`真实C运行 | wheel-*-81349fc.log、packaging-81349fc.json | 全部0；66个源码资源逐字节一致 |
| 三组最终真实run → SCG Preview/Apply/保存重开/正常生成/精确decoder/真实C消费者 | cross-repository/scg-v3-outcomes.json、scg-v3-run-identities.json | **143/143标量一致**；三个真实分析编译和执行均0；不宣称此批重新做过ARM |
| `tools/preview_gui.py --output ... --run .qa/20261101/final-runs-v2/underline-pid.tdrun.json` | final-gui/、final-gui-label/ | 100/125/150%，明暗与紧凑布局；来源查看、算法模态实际渲染 |

最终wheel SHA256：`48741d0d8d5a2f1b60f9fb668a7837ebccf9d6ac1169ce97147344a3db1ba2ac`。完整测试113、GUI专项5、场景15属于不同范围，不相加成一个虚构的全套计数。运行包、参数包与模型摘要分别保留；Underlineside200Ns示例在18秒尚未落地。

轮饱和修复前的实际Plant产生0.00273667N·m·s虚假角动量；修复后按到界时间一致交换。冷气耗尽四个边界用例验证实际力积分为0.004903325N·s，解析变质量火箭方程速度误差最大2.03×10⁻¹¹m/s，耗尽后无额外推力。这里没有把末态质量乘速度近似当作精确冲量。

[正式故障回归](actuator-fault-regression/README.md)隔离加载1983911的修复前physics，使用最终同一组测试，实际结果为5失败→5通过。完整原始日志、UTF-8阅读副本、Git提取命令/源hash、退出码和JUnit均保留，没有改生产源码或放宽期望。

`generated-task-inventory.json`记录`.qa/20261101`生成文件、owner/用途/保留证据与SHA；未清理旧输出、用户数据或原始输入。`tools/record_validation.py`可重新核对当前包与源码；重放应使用新的版本目录，不能覆盖历史证明。

## 真实执行

以下保留1983911阶段的原始验证范围；新的最终范围见上表，不把旧wheel/旧run改称新版本。

| 命令（TD项目.venv Python） | 输出 | 退出/结果 |
|---|---|---|
| `-m pytest -q --basetemp=.test-tmp/commit-1983911` | pytest-commit-1983911.log | 0，104 passed，26.93s |
| `tools/create_examples.py` | examples/ | 0，固定ID和显式假设的完整输入 |
| `tools/verify_examples.py docs/evidence/20261101/final-examples --runs .qa/20261101/final-runs` | examples-final.log、final-examples/matrix.json | 0，15个实际场景；真实C源身份和实际参数包 |
| `-m pip wheel --no-deps --no-build-isolation . -w .qa/20261101/final-wheel` | wheel-build-final.log | 0 |
| `-m pip install --no-deps --target .qa/20261101/final-wheel-install ...whl`，`-I .qa/20261101/wheel_smoke_final.py` | wheel-install-final.log、wheel-smoke-final.log | 0；验证导入来自wheel安装目录，实际SDK在包内，执行C INS/KF6/PID |
| `tools/preview_gui.py`，QT_SCALE_FACTOR=1/1.25/1.5 | preview-scale*.log、scale-*目录 | 0；浅深、模型/任务/结果/920×620截图 |
| `git diff --check` / 已提交副本hash核验 | git/PROVENANCE与测试 | 0 |

`packaging.json`有最终wheel SHA及逐文件与当前src完全一致检查。wheel smoke使用已存在的Python依赖，不是全新操作系统安装或“完全离线pip安装”证明。Linux CI已配置核心/合同测试，当前结论以实际Actions结果另列，Windows桌面不由Linux CI代替。

## 桌面观察

Windows真实`run.py`入口，项目.venv Python3.14.0、PySide6 6.10.1、NumPy2.4.1；正常标题/布局，无硬件访问。使用Computer Use实际点击：打开离线示例；模型对象与真实结构预览；算法草稿改为KF6后Esc，主表仍为“不启用”；重开选KF6/PID后Apply，主表同一实例更新；运行中取消在30%停止，未发布结果；再完整运行，实际最高117.1777m/落地10.865561s；结果轨迹与估计高度；普通文件对话框导出参数成功；导入invalid_version包弹出VERSION字段错误，原装配仍保留。

随后实际导入200Ns Underline包并完整运行，比较117.18m与382.98m两次真实结果、移动回放轴、保存并重开工程；读取只读推力曲线和来源；导入ORK缺项后点击列表，实际定位到Fins对象，再丢弃测试草稿。证据为desktop-compare-final.jpg、desktop-motor-source-440db63.jpg、desktop-ork-missing-locate.jpg。来源图早期单位与图例重叠在81349fc修复，final-gui-label为该修复后的离屏证据。

截图desktop-model-final.jpg、desktop-results-final.jpg来自实际窗口；最初desktop-results.jpg来自较早无控制示例。scale-*与final-gui*均为Qt offscreen渲染，不冒充桌面点击。保存结果与导出记录位于受控`.qa/20261101/`；没有提交用户其他应用内容。

SCG另外使用其真实`apps/SCG/main.py --lang zh_CN --theme light`入口，原生Windows桌面检查三页、双custom未导入阻断、无线双端草稿与取消、唯一INS属性及范围。cross-repository/scg-desktop-*是实际截图；它们不替代该仓库的QTest模型零写入断言或ARM/硬件验证。

Qt自动交互测试另覆盖工程保存/打开失败保持、取消草稿、后台异常/取消、历史结果标识和文件往返。尚未完成独立Windows安装器、其他OS桌面、全部辅助技术/键盘逐项验收，不把现有截图当这些证明。

## 失败历史及处理

- pytest-full.log：74通过、1失败，测试中的QTest等待持有GIL阻塞Pythonworker；改用让出GIL的有界等待，应用正常事件循环未使用该等待。
- pytest-full-v2.log：77通过（当时范围）；pytest-integration-v3.log：97通过（当时范围）；pytest-final.log：102通过（还未纳入最后2个ORK负例）。这些不拼接为104；104是冻结代码完整重跑。
- examples.log：早期增强核倾斜先验因float32构造旋转矩阵再提升到double，触发严格正交误差门槛。宿主适配修为double归一四元数直接构造矩阵；未弱化C核检查，最终矩阵七算法有实际输出。
- 辅助传感器接入时一次局部17通过1失败：NumPy bool不能JSON保存；气压采样明确转换Python float后修复。该失败原输出存在会话记录，最终存储回归通过；不伪造不存在的原始日志文件。
- 首个wheel包含最后ORK修复前的importers.py；逐文件比对发现后重建final-wheel，保留两次构建日志。最终wheel源完全一致。
- Underline schema工作目录CRLF与提交LF曾导致副本hash不一致；统一固定字节与.gitattributes，现21项import回归包含独立hashgate，最终提交字节核验。
- 更换已锁定的Python/NumPy版本会改变算法实现身份，旧run参数导出被拒绝是预期；SCG v2保留这次环境差异拒绝记录。

没有硬件/飞行试验、导航准确性资格或全程序栈证明。无控制回收伞模型，示例结束不等于可部署飞行器。所需软件依赖安装成功，本子任务没有遇到授权拒绝；没有推送SilverStar/Underline。
