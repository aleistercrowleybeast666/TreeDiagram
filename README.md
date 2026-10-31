# TreeDiagram

**当前为 FLP 风格的简体中文 GUI 外壳，业务定位待用户确定。**

## 启动

在本目录双击 `TreeDiagram.cmd`，或运行：

```powershell
cd D:\python_software\TreeDiagram
python -B run.py
```

依赖 Python 3.11+、PySide6 6.8+（小于 7）。本机已验证 Python 3.14.0 / PySide6 6.10.1，直接复用已安装环境；未创建虚拟环境、未安装大依赖、未复制其他仓库。测试另外使用已有 pytest 9.1.1。

## 用户决定与定位证据

本轮任务转述的最新用户原话是：

> Treediagram可以就按照现在flp那个样子先搭一个gui吧，具体定位我下午想想。这几天我事情比较多，先把已经决定的，只用我判断细节不用决定大方向的做了。

据此，当前只确定界面外观、基础工程操作和明确占位；导航页的名称也属于可调整的外壳，不表示业务已经定案。

任务携带的历史说明将 TreeDiagram 放在与 UNDERLINE/SilverStar 并列的仿真软件族中；这是本轮提供的背景，**没有在本机检索到可独立核验的原始设计正文**。Flight/SIL/Core 拆分仅属旧助手建议，未采纳；TreeDiagram 也未被解释为树状图编辑工具。

本机核查情况（2026-10-13）：

- 工作开始前，`D:\python_software` 没有 TreeDiagram 同名目录；相邻项目的浅层文档未命中该名称。
- 默认 `.codex/memories`、`memories_extensions` 为空；所检查的工作目录/摘要位置未找到 `memory_summary.md`。本机会话记录中未检索到 TreeDiagram 用户/助手正文。个人上下文服务不可用，源会话读取未返回历史正文。
- 读取全局 `C:\Users\chdxm\.codex\AGENTS.md` 的命名/结果枚举规范；检查可用 `.agents/skills`，未发现 TreeDiagram 专属约定。
- 只读查看 FLP 的 `AGENTS.md`、两个 GUI 规范、`ui/main_window.py` 与 `ui/theme.py`，确认其深蓝顶栏/侧栏、190 px 导航、文件菜单集中操作、浅深主题和稳定窗口标题。未修改相邻工程。

## 实际可用

- 深蓝顶栏、左侧导航、中央工作区、状态栏，浅色/深色即时切换。
- 固定窗口标题 `TreeDiagram`，顶栏显示版本、当前工程和未保存标记。
- 工程名称与备注编辑；文件菜单支持新建、打开、保存、另存为和退出。
- `Ctrl+N` / `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S`；未保存更改提供保存、放弃、取消。
- 数据、运行配置、结果三页明确显示“占位 / 待确定 / 未启用”，没有虚假的计算按钮。
- 概览和占位页可滚动；统一中文字体、菜单、表格和主题下拉样式。

当前只提供简体中文。主题为本次会话设置，重启回到浅色；尚未增加偏好配置服务、主题持久化或英语切换。

## 工程文件与数据安全

`.tdproj` 是 UTF-8 JSON，顶层 `format` 为 `TreeDiagramProject`，`schema_version` 为整数 `1`。当前 GUI 只编辑名称和备注；新工程的数据/运行配置/运行历史为空，不自动装入样例或选择业务插件。工程不依赖机器绝对路径。

保存先做结构与数值校验，再写同目录临时文件、刷新文件并原子替换。覆盖前将上一版有效内容原子写入同名 `.bak`。文件摘要检测外部修改，`.lock` 防止本应用并发保存；不兼容版本、重复/未知字段、非有限数值、损坏或超限文件均拒绝读取或覆盖。文件上限 4 MiB，不自动截断数据。

打开失败不替换当前工程；保存失败保留未保存状态。`.bak` 是单个上一版，不是无限版本历史。恢复时可通过“所有文件”打开 `.bak`，再另存为新 `.tdproj`。若异常退出遗留 `.lock`，确认没有其他实例正在保存后再手工处理；程序不擅自删除未知锁。摘要/锁不能阻止不遵守锁的外部程序在保存瞬间写同一文件。

## 保留但未接入的草案

范围收窄前已写的 `core/jobs.py`、`core/plugins.py` 及数学数据类型已保留，GUI **不导入、不启动**这些后台功能。纯数学正弦插件、插件注册和协作式线程生命周期只是初步通用草案，不是已验收的业务能力。本轮没有继续扩展其架构或为其定义产品方向。

没有实现具体仿真业务、物理内核、发动机内部仿真、推进剂设计优化、飞行制导/控制算法、硬件连接、FLP 解码/回放、业务导入/导出、插件安装或复杂调度。本轮也不认定需要 Flight/SIL/Core 子产品。

## 文件结构

```text
run.py / TreeDiagram.cmd     源码启动入口
src/treediagram/ui.py        GUI 外壳与工程操作
src/treediagram/theme.py     独立浅深主题与系统字体
src/treediagram/core/        工程格式/会话；保留的后台草案
tests/                      必要 GUI 与工程安全测试
tools/preview_gui.py         渲染本窗口的预览截图
docs/GUI_STYLE_GUIDE.md      本项目最小外观规范
```

## 验证与截图

2026-10-13，`python -B -m pytest -q`：**13 项通过**。覆盖中文保存往返、schema/损坏/重复字段拒绝、外部修改冲突、原子替换失败保留原文件、未保存编辑保留、文件选择取消、新建/关闭取消、保存失败不切换、导航、920×620 / 1180×780 / 1440×900 缩放、浅深主题与真实中文字形。

离屏测试显式引用 Windows 自带的微软雅黑字体文件，防止 offscreen 平台只渲染方框；不复制字体。源码语法检查通过。另通过实际 `App_Main()` 入口在 Windows Qt 平台启动 1180×780 可见窗口，截图成功后自动正常关闭；原生截图为 `.qa/native-light.png`。

```powershell
python -B -m pytest -q
python -B tools/preview_gui.py
```

测试临时文件仅在本目录 `.test-tmp`；截图只在 `.qa`，均不属于工程数据或提交内容。预览脚本输出六张界面图：

- `.qa/light-overview.png`、`.qa/dark-overview.png`
- `.qa/light-placeholder.png`、`.qa/dark-placeholder.png`
- `.qa/light-compact.png`、`.qa/dark-compact.png`

工程独立于 SilverStar/UNDERLINE，未推送、未发布。后续只需用户确定 TreeDiagram 具体定位，再调整占位页及底层取舍。

