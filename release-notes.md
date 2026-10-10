# Overlap Helper v1.2.0

本项目由纯 AI（OpenAI Codex）编写与适配，需求由用户提出。

- 依据本机 Maya 2023.3 原版实际结果修正关键帧偏移、约束和粒子跟随流程。
- 同步 Physics、Cus、Scale、Overshoot、Loop、Ignore First 和多条 Hierarchy 的原版行为。
- 修复动力学撤销残留、已有解算器保护及位移约束通道被意外插入关键帧的问题。
- Maya 2025.3 与 2027.1 各通过 48 项自动检查、14 项 GUI 检查和 23 组逐帧对照；最大误差 1.07×10⁻¹⁴ cm / 1.02×10⁻⁷ 度。
- 安装器自动备份旧包并重新加载。下载 ZIP、完整解压，将 install.py 拖入 Maya 视图。

仅通过 GitHub Releases 发布安装 ZIP。Maya 2026 未实机验证；数值一致性结论限于已测场景。
