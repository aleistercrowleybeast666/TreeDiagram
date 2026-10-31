# 来源与许可

TreeDiagram原创代码采用Apache-2.0（根LICENSE）；历史GUI源码由原工作区初始提交保留。SilverStar固定C数学代码与契约保留SDK/LICENSE和manifest来源/逐文件hash。Underline导出合同、validator及合成golden由同系列Underline项目取得，保留LICENSE-UNDERLINE和PROVENANCE.json；副本不是第二权威。

运行依赖由pip单独安装，本仓库不重新打包其二进制：Python（PSF）、NumPy（BSD-3-Clause及其发行包bundled notices）、SciPy（BSD-3-Clause及其发行包bundled notices）、PySide6/Qt（LGPL-3.0/GPL-3.0或商业许可，按实际分发条件）、jsonschema（MIT）、defusedxml（PSF）。测试pytest为MIT。具体安装发行包的license文件随包保留；含BLAS、编译器runtime等的轮子应以其第三方清单为准，不能仅用顶层BSD代替所有依赖义务。GCC仅用于本地编译宿主库，未随仓库分发。

RocketPy、MAPLEAF、AeroVECTOR、ActiveRocketPy、OpenRocket、RocketSerializer和JSBSim仅为设计参考，本后端没有纳入其代码，不将其许可证重标为Apache。OpenRocket测试XML是依公开格式手工写的合成fixture，不是复制的用户模型。所有motor测试向量是Underline可复现合成数据，非真实台架/飞行记录，无精度或标定资格声明。

微软字体从本机系统使用，不复制进仓库；Qt绘制的本产品截图用于测试证据。完整外部依赖商业再分发审查未执行，本仓库没有制作闭源捆绑安装器。
