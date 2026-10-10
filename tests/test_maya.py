import math
import unittest
from unittest import mock

import maya.cmds as cmds
from maya.api import OpenMaya as om

from overlap_motion import core


def position(node, time):
    cmds.currentTime(time)
    return cmds.xform(node, query=True, worldSpace=True, rotatePivot=True)


def quaternion(node, time):
    cmds.currentTime(time)
    return om.MTransformationMatrix(om.MMatrix(cmds.xform(
        node, query=True, worldSpace=True, matrix=True))).rotation(asQuaternion=True)


def linear_keys(node, attribute, values):
    for frame, value in values:
        cmds.setKeyframe(node, attribute=attribute, time=frame, value=value,
                         inTangentType='linear', outTangentType='linear')


class MayaTests(unittest.TestCase):
    def setUp(self):
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(time='film', angle='deg', linear='cm')
        cmds.autoKeyframe(state=False)

    def moving_control(self):
        node = cmds.createNode('transform', name='control')
        linear_keys(node, 'translateX', [(1, 0), (11, 10)])
        return node

    def bake_translation(self, nodes, **kwargs):
        options = dict(start=1, end=11, mode='delay', delay=2, stagger=0,
                       rotation=False, translation=True)
        options.update(kwargs)
        return core.bake(nodes, **options)

    def test_delayed_world_motion_and_source_curve_survive_mute_and_delete(self):
        node = self.moving_control()
        curve = cmds.listConnections(node + '.translateX', type='animCurve')[0]
        keys = cmds.keyframe(curve, query=True, valueChange=True)
        layer = self.bake_translation([node])
        self.assertAlmostEqual(position(node, 6)[0], 3, places=5)
        self.assertEqual(cmds.keyframe(curve, query=True, valueChange=True), keys)
        cmds.animLayer(layer, edit=True, mute=True)
        self.assertAlmostEqual(position(node, 6)[0], 5)
        cmds.delete(layer)
        self.assertAlmostEqual(position(node, 6)[0], 5)
        self.assertEqual(cmds.keyframe(curve, query=True, valueChange=True), keys)

    def test_layer_has_no_effect_outside_range(self):
        node = self.moving_control()
        layer = self.bake_translation([node], start=3, end=8)
        self.assertAlmostEqual(position(node, 2)[0], 1)
        self.assertAlmostEqual(position(node, 9)[0], 8)
        self.assertEqual(cmds.getAttr(layer + '.weight', time=2.9), 0)
        self.assertEqual(cmds.getAttr(layer + '.weight', time=3), 1)
        self.assertEqual(cmds.getAttr(layer + '.weight', time=8), 1)
        self.assertEqual(cmds.getAttr(layer + '.weight', time=9), 0)
        self.assertEqual(cmds.getAttr(layer + '.weight', time=8.5), 0)
        self.assertAlmostEqual(position(node, 8.5)[0], 7.5)

    def test_one_undo_restores_scene_and_user_state(self):
        node = self.moving_control()
        cmds.currentTime(4)
        cmds.select(node)
        cmds.autoKeyframe(state=True)
        before = set(cmds.ls())
        layer = self.bake_translation([node])
        self.assertEqual(cmds.currentTime(query=True), 4)
        self.assertTrue(cmds.autoKeyframe(query=True, state=True))
        self.assertEqual(cmds.ls(selection=True), [node])
        cmds.undo()
        self.assertFalse(cmds.objExists(layer))
        self.assertEqual(set(cmds.ls()), before)
        self.assertAlmostEqual(position(node, 6)[0], 5)

    def test_child_world_delay_with_rotating_parent_and_unordered_input(self):
        parent = cmds.createNode('transform', name='parent')
        child = cmds.createNode('transform', name='child', parent=parent)
        cmds.setAttr(child + '.translateX', 5)
        linear_keys(parent, 'rotateZ', [(1, 0), (11, 60)])
        expected_parent = quaternion(parent, 4)
        expected_child = quaternion(child, 3)
        layer = core.bake([child, parent], 1, 11, mode='delay', delay=3,
                          stagger=1, rotation=True, translation=False)
        # List order determines delay; evaluation order must still be parent-first.
        actual_parent = quaternion(parent, 7)
        actual_child = quaternion(child, 7)
        self.assertAlmostEqual(abs(actual_parent.x * expected_child.x + actual_parent.y * expected_child.y +
                                   actual_parent.z * expected_child.z + actual_parent.w * expected_child.w), 1, places=5)
        self.assertAlmostEqual(abs(actual_child.x * expected_parent.x + actual_child.y * expected_parent.y +
                                   actual_child.z * expected_parent.z + actual_child.w * expected_parent.w), 1, places=5)
        self.assertTrue(cmds.objExists(layer))

    def test_parent_translation_generates_swing_on_unkeyed_control(self):
        root = cmds.createNode('transform', name='root')
        node = cmds.createNode('transform', name='tail', parent=root)
        linear_keys(root, 'translateY', [(1, 0), (3, 0), (4, 3), (31, 3)])
        core.bake([node], 1, 31, delay=0, response=12, damping=0.3)
        cmds.currentTime(4)
        self.assertLess(cmds.getAttr(node + '.rotateZ'), -5)
        self.assertAlmostEqual(cmds.getAttr(node + '.translateX'), 0)

    def test_frozen_axes_pivots_rotation_order_and_scaled_parent(self):
        root = cmds.createNode('transform', name='root')
        cmds.setAttr(root + '.rotate', 12, 22, -10)
        cmds.setAttr(root + '.scale', 2, 2, 2)
        node = cmds.createNode('transform', name='control', parent=root)
        cmds.setAttr(node + '.rotateAxis', 10, 20, 30)
        cmds.setAttr(node + '.rotatePivot', 1, 2, 0)
        cmds.setAttr(node + '.rotateOrder', 4)
        linear_keys(node, 'rotateY', [(1, 20), (11, 70)])
        linear_keys(node, 'translateX', [(1, 1), (11, 11)])
        expected_pos, expected_q = position(node, 4), quaternion(node, 4)
        core.bake([node], 1, 11, mode='delay', delay=2, translation=True)
        actual_pos, actual_q = position(node, 6), quaternion(node, 6)
        for a, b in zip(actual_pos, expected_pos):
            self.assertAlmostEqual(a, b, places=4)
        self.assertAlmostEqual(abs(actual_q.x * expected_q.x + actual_q.y * expected_q.y +
                                   actual_q.z * expected_q.z + actual_q.w * expected_q.w), 1, places=5)

    def test_joint_orientation_is_preserved(self):
        node = cmds.createNode('joint', name='joint')
        cmds.setAttr(node + '.jointOrient', 15, 30, 10)
        linear_keys(node, 'rotateZ', [(1, 0), (11, 50)])
        expected_q = quaternion(node, 4)
        core.bake([node], 1, 11, mode='delay', delay=2)
        actual_q = quaternion(node, 6)
        self.assertAlmostEqual(abs(actual_q.x * expected_q.x + actual_q.y * expected_q.y +
                                   actual_q.z * expected_q.z + actual_q.w * expected_q.w), 1, places=5)
        for actual, expected in zip(cmds.getAttr(node + '.jointOrient')[0], (15, 30, 10)):
            self.assertAlmostEqual(actual, expected)

    def test_offset_parent_matrix_and_uniform_scale(self):
        parent = cmds.createNode('transform', name='parent')
        cmds.setAttr(parent + '.scale', 2, 2, 2)
        node = cmds.createNode('transform', name='control', parent=parent)
        offset = om.MTransformationMatrix()
        offset.setRotation(om.MEulerRotation(0.2, 0.4, 0.1))
        offset.setTranslation(om.MVector(3, 1, 0), om.MSpace.kTransform)
        cmds.setAttr(node + '.offsetParentMatrix', *list(offset.asMatrix()), type='matrix')
        linear_keys(node, 'rotateZ', [(1, 0), (11, 40)])
        linear_keys(node, 'translateX', [(1, 0), (11, 10)])
        expected_pos, expected_q = position(node, 4), quaternion(node, 4)
        core.bake([node], 1, 11, mode='delay', delay=2, translation=True)
        actual_pos, actual_q = position(node, 6), quaternion(node, 6)
        for a, b in zip(actual_pos, expected_pos):
            self.assertAlmostEqual(a, b, places=4)
        self.assertAlmostEqual(abs(actual_q.x * expected_q.x + actual_q.y * expected_q.y +
                                   actual_q.z * expected_q.z + actual_q.w * expected_q.w), 1, places=5)

    def test_nonuniform_or_mirrored_parent_rejected_without_scene_mutation(self):
        parent = cmds.createNode('transform', name='parent')
        node = cmds.createNode('transform', name='control', parent=parent)
        before = set(cmds.ls())
        for scale in [(1, 2, 1), (-1, 1, 1)]:
            cmds.setAttr(parent + '.scale', *scale)
            with self.subTest(scale=scale), self.assertRaises(ValueError):
                core.bake([node], 1, 11)
            self.assertEqual(set(cmds.ls()), before)

    def test_existing_animation_layer_evaluated_and_preserved(self):
        node = self.moving_control()
        existing = cmds.animLayer('Existing', override=True)
        cmds.animLayer(existing, edit=True, attribute=node + '.translateX')
        for time, value in [(1, 10), (11, 20)]:
            cmds.setKeyframe(node, attribute='translateX', animLayer=existing,
                             time=time, value=value, noResolve=True,
                             inTangentType='linear', outTangentType='linear')
        layer = self.bake_translation([node])
        self.assertAlmostEqual(position(node, 6)[0], 13, places=5)
        cmds.animLayer(layer, edit=True, mute=True)
        self.assertAlmostEqual(position(node, 6)[0], 15, places=5)

    def test_solo_layer_rejected_instead_of_silently_suppressing_output(self):
        node = self.moving_control()
        layer = cmds.animLayer('SoloLayer', override=True)
        cmds.animLayer(layer, edit=True, attribute=node + '.translateX', solo=True)
        before = set(cmds.ls())
        with self.assertRaisesRegex(ValueError, 'Solo'):
            self.bake_translation([node])
        self.assertEqual(set(cmds.ls()), before)
        self.assertTrue(cmds.animLayer(layer, query=True, solo=True))

    def test_locked_or_constrained_channels_fail_before_changes(self):
        node = self.moving_control()
        cmds.setAttr(node + '.translateY', lock=True)
        before = set(cmds.ls())
        with self.assertRaises(ValueError):
            self.bake_translation([node])
        self.assertEqual(set(cmds.ls()), before)
        cmds.setAttr(node + '.translateY', lock=False)
        target = cmds.createNode('transform', name='target')
        cmds.orientConstraint(target, node)
        before = set(cmds.ls())
        with self.assertRaises(ValueError):
            core.bake([node], 1, 11)
        self.assertEqual(set(cmds.ls()), before)

    def test_write_failure_rolls_back_all_generated_nodes(self):
        node = self.moving_control()
        before = set(cmds.ls())
        original = cmds.setKeyframe
        calls = [0]

        def fail_during_write(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 8:
                raise RuntimeError('injected keyframe write failure')
            return original(*args, **kwargs)

        with mock.patch.object(core.cmds, 'setKeyframe', side_effect=fail_during_write):
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                self.bake_translation([node])
        self.assertEqual(set(cmds.ls()), before)
        self.assertAlmostEqual(position(node, 6)[0], 5)

    def test_invalid_inputs_do_not_modify_scene(self):
        node = self.moving_control()
        before = set(cmds.ls())
        for options in [dict(start=11, end=1), dict(start=1.5), dict(delay=-1),
                        dict(strength=float('nan')), dict(rotation=False, translation=False)]:
            base = dict(start=1, end=11)
            base.update(options)
            with self.subTest(options=options), self.assertRaises(ValueError):
                core.bake([node], **base)
        with self.assertRaises(ValueError):
            core.bake([], 1, 11)
        self.assertEqual(set(cmds.ls()), before)

    def test_cycle_output_matches_endpoints(self):
        node = cmds.createNode('transform', name='control')
        linear_keys(node, 'translateY', [(1, 0), (11, 4), (21, 0), (31, -4), (41, 0)])
        core.bake([node], 1, 41, cycle=True, translation=True)
        p0, q0 = position(node, 1), quaternion(node, 1)
        p1, q1 = position(node, 41), quaternion(node, 41)
        for a, b in zip(p0, p1):
            self.assertAlmostEqual(a, b, places=5)
        self.assertAlmostEqual(abs(q0.x * q1.x + q0.y * q1.y + q0.z * q1.z + q0.w * q1.w), 1, places=5)


if __name__ == '__main__':
    unittest.main()
