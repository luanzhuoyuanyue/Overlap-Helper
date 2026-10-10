# Overlap 还原依据

数值基准来自本机 Maya 2023.3 中实际运行的原加密 OverlapHelper，而非从演示视频估计运动。原始模块路径在本次记录环境为 `2026-08-04/e-overlaphelper/outputs/OverlapHelper/39/overlapFile.py`。

记录了原版创建 locators、aim/parent constraints、关键帧偏移、nParticle goal 的调用参数，以及 23 组场景每帧的平移和旋转。基准只包含数值和测试场景参数；安装包不包含原插件的加密模块或运行时。

原版 GUI 在 Maya 2023.3 中实际打开并检查：smoothness/Scale/Overshoot 默认值 3/1/10；Physics 重置 smoothness 为 8，范围 2–9，关闭重置为 3；Cus 默认 Y，允许多个轴同时勾选；普通旋转中 Ignore First 在 Physics 下保持可用；Trans 禁用 Cus、Scale 和 Ignore First，重置三个轴。数字输入可扩大滑块上限。

Maya 2025.3、2027.1 中重建对应流程后，23 组逐帧数据均在 0.0001 cm/度内。测试结果见 `../验收报告.md` 和 `../qa/`。旧版 `core` / `solver` 作为兼容 API 保留，Overlap 界面改用 `legacy` 的原版流程；不再调用独立滤波器生成界面结果。

仅包含 Overlap，不含 Cotroller。允许较安全的输入拒绝和专属动力学节点管理，避免原版清理固定名称节点时误删用户对象。这些边界已列在使用说明中。
