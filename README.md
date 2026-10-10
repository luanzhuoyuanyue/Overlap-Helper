# Overlap Helper · Overlap 页 1.2

**本项目由纯 AI（OpenAI Codex）编写与适配。** 需求由用户提出，代码实现、界面适配、文档整理和测试执行均由 AI 完成。实际验证范围见验收报告。

## 下载

仅通过 [GitHub Releases](https://github.com/luanzhuoyuanyue/Overlap-Helper/releases/tag/v1.2.0) 提供安装 ZIP。解压完整文件后，将 `install.py` 拖入 Maya 三维视图，旧包会自动备份。

Maya 2025–2027 适配版，保留完整 Python 源码，仅包含 Overlap 功能。1.2 按本机 Maya 2023.3 原版的实际运算结果修正关键帧偏移、约束和粒子目标跟随。

本机 Maya 2025.3、2027.1 均已完成图形界面验证和 48 项自动检查。23 组原版对照全部通过，最大通道误差低于 0.0001 cm / 度。Maya 2026 本机未安装，未实机验证。

解压整个 ZIP，将 `install.py` 拖入 Maya 三维视图。安装器会备份旧包、更新 OH 按钮，并重新加载新代码。各 Maya 版本分别安装一次。

- [使用说明](使用说明.md)：参数和操作。
- [验收报告](验收报告.md)：本机环境、逐帧对照与限制。
- [还原依据](docs/overlap-reference.md)：原版行为和验证来源。
- `qa/`：两版测试日志、逐帧误差记录和实际界面截图。
- `tests/fixtures/`：从 Maya 2023.3 原版记录的数值基准。

```python
import overlap_motion
print(overlap_motion.__version__)  # 1.2.0
overlap_motion.show()
```

自动检查：在本目录运行对应版本的 `mayapy.exe -B tests/run_maya.py`。GUI 检查脚本 `tests/gui_smoke.py` 只可在独立测试配置与空场景启动时使用。
