"""Selection and parameter behavior of the original Overlap page."""
import math

from maya import cmds
from maya.api import OpenMaya as om

from . import core
from . import legacy


def selected_controls(hierarchy=False, ignore_first=False, roots=None):
    selected = roots if roots is not None else cmds.ls(selection=True, long=True, transforms=True) or []
    nodes = []
    for root in selected:
        def walk(node):
            result = []
            for child in cmds.listRelatives(node, children=True, fullPath=True, type='transform') or []:
                result.append(child)
                result.extend(walk(child))
            return result
        descendants = walk(root) if hierarchy else []
        # Offset groups in curve rigs are not animation controls. Bare transform
        # chains and joint chains remain valid, as in the original examples.
        has_curves = any(cmds.listRelatives(n, shapes=True, type='nurbsCurve')
                         for n in [root] + descendants)
        chain = [root] + [n for n in descendants if not has_curves or
                         cmds.nodeType(n) == 'joint' or
                         cmds.listRelatives(n, shapes=True, type='nurbsCurve')]
        if hierarchy and cmds.nodeType(root) == 'joint':
            chain = [n for n in chain if cmds.nodeType(n) == 'joint']
        elif hierarchy and has_curves:
            chain = [n for n in chain if cmds.listRelatives(n, shapes=True, type='nurbsCurve')]
        if ignore_first and hierarchy:
            chain = chain[1:]
        nodes.extend(n for n in chain if n not in nodes)
    return nodes[1:] if ignore_first and not hierarchy else nodes


def _aims(nodes, start, custom, axes):
    """Use the chain direction, or the selected local offset axis in Cus mode."""
    original_time = cmds.currentTime(query=True)
    try:
        cmds.currentTime(start)
        poses = {node: core._world_pose(node) for node in nodes}
        result = {}
        for node in nodes:
            p, q = poses[node]
            relatives = [other for other in nodes if other.startswith(node + '|')]
            previous = [other for other in nodes if node.startswith(other + '|')]
            neighbor = min(relatives, key=lambda n: n.count('|')) if relatives else None
            if neighbor:
                direction = om.MVector(*poses[neighbor][0]) - om.MVector(*p)
            elif previous:
                parent = max(previous, key=lambda n: n.count('|'))
                direction = om.MVector(*p) - om.MVector(*poses[parent][0])
            else:
                direction = om.MVector(0, 0, 0)
            length = direction.length() if direction.length() > 1e-5 else 5.0
            if custom:
                aim = core.AXES[axes[0]]
            elif direction.length() > 1e-5:
                local = direction.rotateBy(om.MQuaternion(*q).inverse()).normal()
                aim = tuple(local)
            else:
                aim = core.AXES['Y']
            result[node] = (aim, length)
        return result
    finally:
        cmds.currentTime(original_time)


def create(rotation=True, custom=False, physics=False, axes=('X', 'Y', 'Z'),
           smoothness=3.0, scale=1.0, overshoot=10.0, ignore_first=False,
           hierarchy=False, loop=False, add_to_layer=True):
    """Bake the current selection over Maya's current playback range.

    Return the result layer, or None for a successful direct bake.
    All exceptions reach the caller; None never represents a silent failure.
    """
    if not all(math.isfinite(v) for v in (smoothness, scale, overshoot)):
        raise ValueError('参数必须为有效数值。')
    if smoothness < 0.1 or scale < 0.1 or overshoot < 1:
        raise ValueError('smoothness 最小 0.1，Scale 最小 0.1，Overshoot 最小 1。')
    if not axes or any(axis not in ('X', 'Y', 'Z') for axis in axes):
        raise ValueError('请至少勾选一个 Axis。')
    if custom and not rotation:
        raise ValueError('Cus 模式需要 Rotat。')
    roots = cmds.ls(selection=True, long=True, transforms=True) or []
    groups = [selected_controls(True, roots=[root]) for root in roots] if hierarchy else [selected_controls()]
    all_nodes = [n for group in groups for n in group]
    nodes = selected_controls(hierarchy, ignore_first) if ignore_first else all_nodes
    if not nodes:
        raise ValueError('请先在 Maya 中选择控制器；忽略首项后也必须保留控制器。')
    start = cmds.playbackOptions(query=True, minTime=True)
    end = cmds.playbackOptions(query=True, maxTime=True)
    if rotation and not custom and any(len(group) < 2 for group in groups):
        raise ValueError('普通 Rotat 模式需要至少两个控制器；单个控制器请使用 Cus。')
    if physics and not 2 <= smoothness <= 9:
        raise ValueError('Physics 模式的 smoothness 范围为 2–9，默认值为 8。')
    output_axes = ('X', 'Y', 'Z') if custom else axes
    attributes = [('rotate' if rotation else 'translate') + axis for axis in output_axes]
    writable = False
    for node in nodes:
        unlocked = [a for a in attributes if not cmds.getAttr(node + '.' + a, lock=True)]
        if unlocked:
            core._validate([node], start, end, unlocked, add_to_layer)
            writable = True
    if not writable:
        raise ValueError('所选 Axis 通道均被锁定，无法生成动画。')
    original_time = cmds.currentTime(query=True)
    selection = cmds.ls(selection=True, long=True) or []
    auto = cmds.autoKeyframe(query=True, state=True)
    evaluation_mode = cmds.evaluationManager(query=True, mode=True)[0]
    if loop and not add_to_layer:
        raise ValueError('Loop 模式请启用 Add to Animation Layer。')
    playback = {key: cmds.playbackOptions(query=True, **{key: True})
                for key in ('minTime', 'maxTime', 'animationStartTime', 'animationEndTime')}
    bake_end = end + (end - start) if loop else end
    op = legacy.Overlap(start, bake_end, rotation, physics, smoothness, scale, overshoot,
                        output_axes, add_to_layer, ignore_first)
    failed = False
    cmds.undoInfo(openChunk=True, chunkName='Overlap Helper')
    try:
        cmds.autoKeyframe(state=False)
        # Explicit particle evaluation under DG is deterministic in both GUI
        # and mayapy. Parallel evaluation can leave particle goals stationary.
        if physics and evaluation_mode != 'off':
            cmds.evaluationManager(mode='off')
        if loop:
            cmds.playbackOptions(maxTime=bake_end)
        cmds.currentTime(start)
        if custom:
            for node in all_nodes:
                tip = cmds.createNode('transform', name='overlapHelperTemp_custom#', parent=node)
                op.temporary.append(tip)
                cmds.setAttr(tip + '.translate' + [a for a in 'XYZ' if a in axes][-1], 5)
                op.bake_chain([node, tip], custom=True)
                op.delete([tip])
        else:
            layers = []
            for group in groups:
                op.layer = None
                op.bake_chain(group)
                if op.layer:
                    layers.append(op.layer)
        if loop and op.layer:
            result_layers = [op.layer] if custom else layers
            curves = [c for layer in result_layers for c in
                      cmds.animLayer(layer, query=True, animCurves=True) or []]
            cmds.keyframe(curves, relative=True, timeChange=-(end - start))
            cmds.cutKey(curves, clear=True, time=(start - (end - start), start - 1))
        return op.layer
    except Exception:
        failed = True
        raise
    finally:
        try:
            op.cleanup()
            cmds.playbackOptions(**playback)
            cmds.select(selection, replace=True) if selection else cmds.select(clear=True)
            cmds.currentTime(original_time)
            cmds.autoKeyframe(state=auto)
            if physics and cmds.evaluationManager(query=True, mode=True)[0] != evaluation_mode:
                cmds.evaluationManager(mode=evaluation_mode)
        finally:
            cmds.undoInfo(closeChunk=True)
            if failed:
                cmds.undo()
