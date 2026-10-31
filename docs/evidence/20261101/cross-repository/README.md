# 跨仓库最终证据副本

本目录只复制已审阅的报告、声明数据、日志和真实Qt图像，不包含生成固件、二进制、虚拟环境或完整SDK工作区。SilverStar生产代码冻结在`09c057a67acfc10e3ff387a4a8821c8ee0e83b0c`，最终证据HEAD为`8b028f280ba01dce0efc697479ef99ec143f7456`；Underline最终本地HEAD为`c1f8ac76f9bbcde1076ef9e48624c920ad161960`。这两个仓库均没有在本轮推送。

| 入口 | 实际范围 |
|---|---|
| [SilverStar中文报告](silverstar/treediagram_20261101/REPORT_ZH.md) | SCG三页、旧工程迁移、S通信、GSHC、安装/GNSS、FLP、USB、生成与验收矩阵 |
| [逐银行资源](silverstar/treediagram_20261101/RESOURCE_SUMMARY.md) | 10个实际构型/候选；使用率、物理及预算余量、保留字节和栈未证明项 |
| [SS-TM字节表](silverstar/treediagram_20261101/ss-tm-wire-v1/WIRE_BYTES_ZH.md) | 唯一合同派生，C/Python golden与16个Host调度场景；不是RF实测 |
| [最终参数回导v4](silverstar/treediagram_algorithms_20261101/v4/README.md) | 3份真实运行，143/143标量，生成decoder及实际C消费者；没有重跑ARM |
| [H743最终v6](silverstar/h7_storage_20261101/v6/DELIVERY.md) | ARM/架构/覆盖完整的Power10/真实analyzer/artifact通过；严格stack失败，critical-contract NOT PROVEN |
| [Underline桥接报告](underline-validation.md) | 原GUI导出插件、headless共用流水线、科学来源修复和379项全套测试 |

`silverstar/treediagram_20261101/gui-offscreen-125-v8`与`gui-offscreen-150-v8`为真实QWidget的中文浅色/英文深色渲染及QTest交互；本目录`scg-desktop-*.jpg`为Windows实际桌面操作。两类证据不同，不能互相冒充。

[copy-manifest.json](copy-manifest.json)逐文件记录来源、实际目标、字节数、工作字节SHA和来源Git blob SHA；复制时检查了已提交原件及其清单。对应局部`.gitattributes`保留原始字节。原SS清单中的建议目标名不替代本目录manifest的实际路径；这里保留源证据的相对目录，使报告交叉链接可用。

SilverStar全部历史失败日志、所有构建命令和完整生成清单保存在本地已提交的`docs/evidence/treediagram_20261101`、`h7_storage_20261101`与`treediagram_algorithms_20261101`。公开副本没有把未复制的旧日志称为已上传；H7的evidence-index保留原日志hash、行号和关键失败内容。

`final-sdk-source-identity.json`保留额外上游原字节检查的false结果；`final-sdk-source-identity-analysis.json`证明32项源码自SDK固定提交至最终接收端未变，25项差异仅为Windows工作副本CRLF与上游Git LF。SDK实际固定字节、manifest与运行身份没有改动。
