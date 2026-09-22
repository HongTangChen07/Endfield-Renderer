# 终末地一键渲染

面向 **GOO 引擎（Goo Engine 4.4.x）** 的中文角色材质配置插件，当前版本 **1.1.4**，已在 Windows / Goo Engine 4.4.3 验证。**不支持普通 Blender、Cycles 或其他 Goo 版本。**

## 功能

- 一键配置终末地风格角色材质，内置尼可、提弗洛斯、索米适配，并支持自定义角色材质映射。
- 自动识别材质用途与已有贴图；缺失的必需辅助图根据基础颜色生成，完整生成程序保留在 `endfield_renderer/maps.py`。
- 独立的一键导入修改器功能；修改器启用并保持可编辑，不烘焙到基础网格。
- 自定义角色提供脸部肤色匹配、面部亮度及法线柔化参数。
- 仅配置角色，不导入环境、舞台或其他角色，不创建相机。优先使用当前日光；缺少时补建角色着色所需日光与控制点。
- 不创建自动备份、不自动回滚或打开其他工程；结果工程默认不另存。没有相机时跳过预览，仍完成角色配置。

## 安装

下载 **[endfield_one_click_1_1_4.zip](https://github.com/HongTangChen07/Endfield-Renderer/releases/download/v1.1.4/endfield_one_click_1_1_4.zip)** 安装包。在 Goo Engine 中打开 **编辑 → 偏好设置 → 插件 → 从磁盘安装**，选择 ZIP 并启用「终末地一键渲染」。安装后，在 3D 视图按 **N → 终末地**。

GitHub 的 **Source code / Download ZIP** 是仓库源码包，请先按下方步骤构建安装包。

选中角色网格，保持「自动识别材质与贴图」开启，设置输出目录后点击「一键终末地渲染」。只需要修改器时，点击「一键导入修改器」。安装与运行无需 MCP 服务或额外 Python 包。

详细说明：[快速开始](endfield_renderer/快速开始.md) · [使用说明与贴图通道](endfield_renderer/README.md)

## 自定义角色与限制

当前按每个角色一个完整网格处理，需要 UV 和区分部位的材质槽；绑定角色需有可识别的头骨，也支持静态网格。分件角色需先自行整理。自动识别结果可在材质映射面板调整。

生成的法线、P、HN 等辅助图是算法估算结果，并非游戏原始贴图；自定义角色的脸型、肤色及高光仍需检查。预览使用场景现有相机。插件包含着色器和修改器资源，不包含角色模型及角色纹理集。

## 从源码打包

构建需要 Python 3.10 或更高版本，仅使用标准库，不需要启动 Goo Engine。在仓库根目录执行：

```sh
python scripts/build_release.py
```

产物位于 `dist/`：插件安装 ZIP 和对应的 SHA-256 校验文件。脚本检查 Python 语法、资源哈希及 ZIP 完整性，仅打包插件代码、中文文档和必需的角色着色资源。

## 发布到 GitHub

1. 将本目录的内容放入仓库根目录，保留 `endfield_renderer/`、`scripts/` 及根目录说明文件。
2. 创建 `v1.1.4` 版本的 Release，将安装包 `endfield_one_click_1_1_4.zip` 放入附件。
3. 发布说明可使用 [RELEASE_NOTES.md](RELEASE_NOTES.md)，原始资源说明保留在 [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)。

## 参考资源说明

参考着色器开发者：**新杨XIYAG**。随附参考资源的原始说明要求非盈利分享、禁止售卖，并在发布简介注明开发者，全文见 [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)。该文件位于仓库层，不进入插件安装 ZIP。仓库未新增 MIT、GPL 等授权声明；第三方角色资产的使用权不由此仓库授予。
