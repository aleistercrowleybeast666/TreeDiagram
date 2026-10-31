# 执行机构边界：修复前失败与修复后通过

同一份最终 `tests/test_physics.py`，选中实际 Plant 的轮饱和/反转 1 例与 RCS 耗尽 4 例：

| 实现 | 原始 pytest 结果 | 退出码 |
|---|---|---:|
| `1983911f419190e80241a4ed851462516a1de737` 的 physics | 5 failed in 2.12s；无 errors/skips | 1（预期失败） |
| 当前 physics，与修复提交 `440db630ac12c5e3ad128623870ef00771c49e25` 内容一致 | 5 passed in 1.86s；无 errors/skips | 0 |

隔离 runner 总退出码为 0，表示成功获得预期的前后结果，不表示修复前测试通过。

命令（仓库 cwd）：

```powershell
.venv/Scripts/python.exe -u docs/evidence/20261101/actuator-fault-regression/run_regression.py
```

runner 使用 `git show` 提取旧 physics 到独立 `.test-tmp/actuator-fault-regression-20261101/`，
已确认该提交就是 `440db63^`；提取文件与 Git 对象 SHA-256 完全相同。它在独立子进程
中加载旧模块，没有 checkout/reset、没有替换当前源码，没有改模型、算法或测试期望。
测试文件在前后运行之间保持逐字节一致。

最终 RCS 测试的额外观测器调用新增可选关键字 `rcs_active=None`。旧实现没有这个签名；
隔离 runner 仅添加接受 **None** 的兼容入口，然后原样调用旧方法。非 None 覆盖会报错。
旧版的推力、质量流率、RK 阶段、事后 clip 全部保留。失败均来自物理断言，没有 TypeError
或人为注入失败。这是“历史 physics + 最终模型/测试”的定点故障复现，不是历史整库回归。

轮在恒质量、未来点火、无重力/气动力/外力矩下饱和并反转，旧实现产生最大
`0.002736666666666679 N·m·s` 的虚假惯性系总角动量。
RCS 测试直接积分实际产生的力，预算为 `0.004903325 N·s`：

| 步长 s | 初始阀门开度 | 旧实现实际排气冲量 N·s |
|---:|---:|---:|
| 0.005 | 1 | 0.006461869855967078 |
| 0.05 | 1 | 0.011111111111111108 |
| 0.005 | 0 | 0.004996894577368034 |
| 0.05 | 0 | 0.013888888888888893 |

修复后同一测试严格检查燃料预算、变量质量火箭方程速度和耗尽后无额外冲量。
未放宽断言，未以 `m_final*v` 近似代替正式冲量检查。

- 可直接阅读的完整输出：[修复前](before.utf8.log)、[修复后](after.utf8.log)。
- 原始 CP936 控制台字节：[before.log](before.log)、[after.log](after.log)；未覆盖原始输出。
  [编码转换与摘要](console-log-encoding.json)说明 UTF-8 文件只是派生阅读副本。
- [精确来源、提取命令、源文件与测试摘要](provenance.json)。
- [真实子进程命令/退出码/时长/日志摘要](commands.json)、[五例机器可读结果](summary.json)。
- JUnit 保留完整断言失败与逐例结果：[before](before.junit.xml)、[after](after.junit.xml)。

本证据无硬件/ARM 操作。已有输出受拒绝覆写保护；重新生成证据须选择新的受控任务目录，
不能删除或覆盖这批正式前后对照。
