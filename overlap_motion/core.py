"""Maya scene sampling and reversible animation-layer baking."""

import math

from maya import cmds
from maya.api import OpenMaya as om

from . import solver


AXES = {'X': (1, 0, 0), 'Y': (0, 1, 0), 'Z': (0, 0, 1),
        '-X': (-1, 0, 0), '-Y': (0, -1, 0), '-Z': (0, 0, -1)}
ROTATION = ['rotateX', 'rotateY', 'rotateZ']
TRANSLATION = ['translateX', 'translateY', 'translateZ']


def ordered_selection():
    """Selected transforms, with ancestors before descendants."""
    return sorted(cmds.ls(selection=True, long=True, type='transform') or [],
                  key=lambda node: node.count('|'))


def _validate(nodes, start, end, attributes, add_to_layer=True):
    if not nodes:
        raise ValueError('请先加载至少一个控制器。')
    if int(start) != start or int(end) != end or end <= start:
        raise ValueError('起止帧必须为整数，结束帧必须大于起始帧。')
    if not attributes:
        raise ValueError('请至少启用旋转或位移。')
    if not cmds.undoInfo(query=True, state=True):
        raise ValueError('请先在 Maya 首选项中启用撤销，再生成动画。')
    solo_layers = [layer for layer in cmds.ls(type='animLayer') or []
                   if cmds.animLayer(layer, query=True, solo=True)]
    if solo_layers:
        raise ValueError('请先关闭动画层的 Solo（独显），否则新结果层不会生效：' + ', '.join(solo_layers))
    result = []
    for node in nodes:
        matches = cmds.ls(node, long=True) or []
        if len(matches) != 1 or cmds.nodeType(matches[0]) not in ('transform', 'joint'):
            raise ValueError('对象不存在、名称不唯一或不是控制器：' + str(node))
        node = matches[0]
        if node in result:
            continue
        for attribute in attributes:
            plug = node + '.' + attribute
            if cmds.getAttr(plug, lock=True) or not cmds.getAttr(plug, keyable=True):
                raise ValueError('通道被锁定或不能打关键帧：' + plug)
            sources = cmds.listConnections(plug, source=True, destination=False) or []
            for source in sources:
                kind = cmds.nodeType(source)
                if not (kind.startswith('animCurveT') or kind.startswith('animBlendNode')):
                    raise ValueError('通道被约束、表达式或其他节点驱动：' + plug)
                if not add_to_layer and kind.startswith('animBlendNode'):
                    raise ValueError('已有动画层的通道请启用“添加到动画层”：' + plug)
        result.append(node)
    return result


def _copy_transform_settings(source, proxy):
    attributes = ['scale', 'shear', 'rotateAxis', 'rotatePivot', 'rotatePivotTranslate',
                  'scalePivot', 'scalePivotTranslate', 'rotateOrder', 'inheritsTransform',
                  'offsetParentMatrix']
    if cmds.nodeType(source) == 'joint':
        attributes += ['jointOrient', 'segmentScaleCompensate', 'inverseScale']
    for attribute in attributes:
        value = cmds.getAttr(source + '.' + attribute)
        plug = proxy + '.' + attribute
        if attribute == 'offsetParentMatrix':
            cmds.setAttr(plug, *value, type='matrix')
        elif isinstance(value, list):
            cmds.setAttr(plug, *value[0])
        else:
            cmds.setAttr(plug, value)


def _world_pose(node):
    position = tuple(cmds.xform(node, query=True, worldSpace=True, rotatePivot=True))
    matrix = om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))
    rotation = om.MTransformationMatrix(matrix).rotation(asQuaternion=True)
    return position, (rotation.x, rotation.y, rotation.z, rotation.w)


def _check_parent_scale(node):
    matrix = om.MMatrix(cmds.getAttr(node + '.parentMatrix[0]'))
    transform = om.MTransformationMatrix(matrix)
    scale = transform.scale(om.MSpace.kTransform)
    shear = transform.shear(om.MSpace.kTransform)
    own_scale = cmds.getAttr(node + '.scale')[0]
    if (min(scale) <= 1e-8 or max(scale) - min(scale) > max(scale) * 1e-5
            or any(abs(value) > 1e-5 for value in shear) or min(own_scale) <= 0):
        raise ValueError('暂不支持父级非均匀缩放、剪切或负缩放，请使用正向等比缩放的控制器层级：' + node)


def _update_progress(interactive, label, amount):
    if interactive:
        if cmds.progressWindow(query=True, isCancelled=True):
            raise RuntimeError('已取消，本次生成已撤销。')
        cmds.progressWindow(edit=True, progress=amount, status=label)


def bake(nodes, start, end, mode='spring', delay=2.0, stagger=1.0, response=12.0,
         damping=0.35, strength=1.0, rotation=True, translation=False, axis='X',
         length=5.0, cycle=False, axes=('X', 'Y', 'Z'), add_to_layer=True,
         amplitude=1.0, aims=None, layer_name='OverlapMotion#', filter_twist=False):
    """Sample evaluated source motion and return a new, undoable override layer.

    List order determines stagger; DAG depth determines write order. Existing
    visible animation layers form part of the sampled input. Mute previous
    results before re-running if you want to start from the original animation.
    """
    if not axes or any(axis_name not in ('X', 'Y', 'Z') for axis_name in axes):
        raise ValueError('请至少选择一个有效的 X / Y / Z 轴。')
    attributes = [attr for attr in ((ROTATION if rotation else []) +
                                   (TRANSLATION if translation else [])) if attr[-1] in axes]
    if not all(math.isfinite(v) for v in (start, end, stagger)) or stagger < 0:
        raise ValueError('帧范围和递增延迟必须为有效数值，递增延迟不能为负。')
    if axis not in AXES:
        raise ValueError('摆动轴必须为 X、Y、Z 或它们的负方向。')
    if not math.isfinite(amplitude) or not 0 <= amplitude <= 10:
        raise ValueError('比例必须在 0–10 之间。')
    # Validate numerical solver options before any scene mutation.
    solver.solve([(0, 0, 0)] * 2, [(0, 0, 0, 1)] * 2, delay=delay,
                 mode=mode, response=response, damping=damping, strength=strength,
                 axis=AXES[axis], length=length, cycle=False)
    nodes = _validate(nodes, start, end, attributes, add_to_layer)
    start, end = int(start), int(end)
    frames = list(range(start, end + 1))
    original_time = cmds.currentTime(query=True)
    original_selection = cmds.ls(selection=True, long=True) or []
    original_auto = cmds.autoKeyframe(query=True, state=True)
    layer_states = {layer: (cmds.animLayer(layer, query=True, selected=True),
                            cmds.animLayer(layer, query=True, preferred=True))
                    for layer in cmds.ls(type='animLayer') or []}
    interactive = not cmds.about(batch=True)
    if interactive:
        cmds.progressWindow(title='重叠动画助手', progress=0, maxValue=100,
                            status='采样原动画…', isInterruptable=True)
    layer = None
    temporary = []
    failed = False
    mutated = False
    cmds.undoInfo(openChunk=True, chunkName='Overlap Helper')
    try:
        cmds.autoKeyframe(state=False)
        samples = {node: ([], []) for node in nodes}
        local_rotations = {node: [] for node in nodes}
        for index, frame in enumerate(frames):
            _update_progress(interactive, '采样原动画…', int(30 * index / len(frames)))
            cmds.currentTime(frame, edit=True, update=True)
            for node in nodes:
                if rotation:
                    _check_parent_scale(node)
                position, quaternion = _world_pose(node)
                samples[node][0].append(position)
                samples[node][1].append(quaternion)
                local_rotations[node].append(cmds.getAttr(node + '.rotate')[0])
        trajectories = {}
        for index, node in enumerate(nodes):
            _update_progress(interactive, '计算重叠运动…', 30 + int(15 * index / len(nodes)))
            aim, tip_length = (aims or {}).get(node, (AXES[axis], length))
            trajectories[node] = solver.solve(*samples[node], delay=delay + index * stagger,
                                              mode=mode, response=response, damping=damping,
                                              strength=strength, axis=aim,
                                              length=tip_length, cycle=cycle,
                                              filter_twist=filter_twist)

        cmds.currentTime(start, edit=True, update=True)
        mutated = True
        if add_to_layer:
            layer = cmds.animLayer(layer_name, override=True, passthrough=True)
            cmds.setAttr(layer + '.rotationAccumulationMode', 1)
            cmds.animLayer(layer, edit=True, attribute=[node + '.' + attr
                                                       for node in nodes for attr in attributes])
            # Step weights keep the source untouched outside the requested interval.
            for time, weight in [(start - 1, 0), (start, 1), (end, 1), (end + 1, 0)]:
                cmds.setKeyframe(layer, attribute='weight', time=time, value=weight,
                                 inTangentType='linear', outTangentType='stepnext' if time == end else 'step')
        else:
            for node in nodes:
                # Insert guard keys without reshaping the surrounding input
                # curve. The adjacent one-frame intervals join the new bake
                # to that curve; all outside integer frames retain the input.
                for guard in (start - 1, end + 1):
                    cmds.setKeyframe(node, attribute=attributes, time=guard, insert=True)
                    cmds.keyTangent(node, attribute=attributes, time=(guard, guard),
                                    edit=True, inTangentType='fixed', outTangentType='fixed')
                cmds.cutKey(node, attribute=attributes, time=(start, end), clear=True)

        proxies = {}
        previous_angles = {}
        angle_unit = om.MAngle.uiUnit()
        for node in nodes:
            target = cmds.createNode('transform', name='overlapMotionTarget#')
            temporary.append(target)
            parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
            args = dict(name='overlapMotionProxy#')
            if parents:
                args['parent'] = parents[0]
            proxy = cmds.createNode(cmds.nodeType(node), **args)
            temporary.append(proxy)
            # Joint creation may connect inverseScale automatically.
            if cmds.nodeType(node) == 'joint':
                for source_plug in cmds.listConnections(proxy + '.inverseScale', source=True,
                                                        destination=False, plugs=True) or []:
                    cmds.disconnectAttr(source_plug, proxy + '.inverseScale')
            _copy_transform_settings(node, proxy)
            if rotation:
                cmds.orientConstraint(target, proxy, maintainOffset=False)
            if translation:
                cmds.pointConstraint(target, proxy, maintainOffset=False)
            proxies[node] = (proxy, target)
            previous_angles[node] = om.MEulerRotation(
                *[om.MAngle(v, angle_unit).asRadians() for v in local_rotations[node][0]],
                cmds.getAttr(node + '.rotateOrder'))

        for index, frame in enumerate(frames):
            _update_progress(interactive, '烘焙动画层…', 45 + int(55 * index / len(frames)))
            cmds.currentTime(frame, edit=True, update=True)
            for node in sorted(nodes, key=lambda n: n.count('|')):
                proxy, target = proxies[node]
                _copy_transform_settings(node, proxy)
                p, q = trajectories[node][0][index], trajectories[node][1][index]
                cmds.setAttr(target + '.translate', *p)
                euler = om.MQuaternion(*q).asEulerRotation()
                cmds.setAttr(target + '.rotate', *[om.MAngle(v).asUnits(angle_unit) for v in euler])
                values = {}
                if rotation:
                    raw = [om.MAngle(v, angle_unit).asRadians() for v in cmds.getAttr(proxy + '.rotate')[0]]
                    order = cmds.getAttr(node + '.rotateOrder')
                    constrained = om.MEulerRotation(*raw, order)
                    # orientConstraint accounts for jointOrient, but not rotateAxis.
                    rotate_axis = om.MEulerRotation(*[om.MAngle(v, angle_unit).asRadians()
                                                       for v in cmds.getAttr(node + '.rotateAxis')[0]])
                    solved = om.MTransformationMatrix(
                        rotate_axis.asMatrix().inverse() * constrained.asMatrix()).rotation()
                    solved.reorderIt(order)
                    solved = solved.closestSolution(previous_angles[node])
                    previous_angles[node] = solved
                    angles = [om.MAngle(v).asUnits(angle_unit) for v in solved]
                    original = local_rotations[node][index]
                    # Equivalent Euler representations can differ by full
                    # turns. Match each delta to the source before scaling it.
                    turn = om.MAngle(2 * math.pi).asUnits(angle_unit)
                    angles = [b + turn * round((a - b) / turn)
                              for a, b in zip(original, angles)]
                    values.update(zip(ROTATION, [a + amplitude * (b - a)
                                                  for a, b in zip(original, angles)]))
                if translation:
                    values.update(zip(TRANSLATION, cmds.getAttr(proxy + '.translate')[0]))
                for attribute, value in values.items():
                    if attribute not in attributes:
                        continue
                    layer_option = dict(animLayer=layer) if layer else {}
                    cmds.setKeyframe(node, attribute=attribute, time=frame,
                                     value=value, noResolve=True, inTangentType='linear',
                                     outTangentType='linear', **layer_option)
                # Re-evaluate before children solve against this parent's result.
                cmds.currentTime(frame, edit=True, update=True)
        return layer
    except Exception:
        failed = True
        raise
    finally:
        try:
            existing = [node for node in temporary if cmds.objExists(node)]
            if existing:
                cmds.delete(existing)
            for name, (selected, preferred) in layer_states.items():
                cmds.animLayer(name, edit=True, selected=selected, preferred=preferred)
            if original_selection:
                cmds.select(original_selection, replace=True)
            else:
                cmds.select(clear=True)
            cmds.currentTime(original_time, edit=True, update=True)
            cmds.autoKeyframe(state=original_auto)
        finally:
            cmds.undoInfo(closeChunk=True)
            if failed and mutated:
                cmds.undo()
            if interactive:
                cmds.progressWindow(endProgress=True)
