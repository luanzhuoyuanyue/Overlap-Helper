"""Original-page workflows, tested with evaluated Maya scene data."""
import math
import unittest
from unittest import mock

from maya import cmds
from overlap_motion import core


class OverlapTests(unittest.TestCase):
    def setUp(self):
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.autoKeyframe(state=False)
        cmds.currentUnit(time='film', angle='deg', linear='cm')
        cmds.playbackOptions(minTime=1, maxTime=31)

    def moving(self):
        node = cmds.createNode('transform', name='control')
        for frame, value in [(1, 0), (4, 0), (5, 8), (31, 8)]:
            cmds.setKeyframe(node, attribute='translateY', time=frame, value=value,
                             inTangentType='linear', outTangentType='linear')
        cmds.select(node)
        return node

    def test_axis_filter_leaves_locked_unselected_channel_untouched(self):
        node = self.moving()
        cmds.setAttr(node + '.translateX', lock=True)
        layer = core.bake([node], 1, 31, rotation=False, translation=True,
                          axes=('Y',), mode='soft', delay=0)
        self.assertLess(cmds.getAttr(node + '.translateY', time=5), 8)
        members = cmds.animLayer(layer, query=True, attribute=True)
        self.assertEqual(len(members), 1)
        self.assertTrue(members[0].endswith('.translateY'))
        self.assertTrue(cmds.getAttr(node + '.translateX', lock=True))

    def test_direct_bake_creates_no_layer_and_one_undo_restores_curve(self):
        node = self.moving()
        curve = cmds.listConnections(node + '.translateY', type='animCurve')[0]
        before = cmds.keyframe(curve, query=True, valueChange=True)
        core.bake([node], 1, 31, rotation=False, translation=True, axes=('Y',),
                  mode='soft', delay=0, add_to_layer=False)
        self.assertFalse(cmds.ls(type='animLayer'))
        self.assertLess(cmds.getAttr(node + '.translateY', time=5), 8)
        cmds.undo()
        self.assertEqual(cmds.keyframe(curve, query=True, valueChange=True), before)

    def test_direct_write_failure_rolls_back_original_keys(self):
        node = self.moving()
        curve = cmds.listConnections(node + '.translateY', type='animCurve')[0]
        times = cmds.keyframe(curve, query=True, timeChange=True)
        values = cmds.keyframe(curve, query=True, valueChange=True)
        original = cmds.setKeyframe
        calls = [0]

        def fail(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 5:
                raise RuntimeError('direct-write-failure')
            return original(*args, **kwargs)

        with mock.patch.object(core.cmds, 'setKeyframe', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'direct-write-failure'):
                core.bake([node], 1, 31, rotation=False, translation=True,
                          add_to_layer=False)
        self.assertEqual(cmds.keyframe(curve, query=True, timeChange=True), times)
        self.assertEqual(cmds.keyframe(curve, query=True, valueChange=True), values)
        self.assertFalse(cmds.ls('overlapMotionProxy*', 'overlapMotionTarget*'))

    def test_hierarchy_uses_curve_controls_and_skips_offset_groups(self):
        from overlap_motion import overlap
        root = cmds.circle(name='root', constructionHistory=False)[0]
        offset = cmds.createNode('transform', name='offset', parent=root)
        child = cmds.circle(name='child', constructionHistory=False)[0]
        cmds.parent(child, offset)
        cmds.select(root)
        nodes = overlap.selected_controls(hierarchy=True)
        self.assertEqual([node.rsplit('|', 1)[-1] for node in nodes], ['root', 'child'])
        self.assertEqual(overlap.selected_controls(hierarchy=True, ignore_first=True), nodes[1:])

    def test_ignore_first_in_manual_selection_retains_remaining_controls(self):
        from overlap_motion import overlap
        first = cmds.createNode('transform', name='first')
        second = cmds.createNode('transform', name='second')
        cmds.select(first, second)
        self.assertEqual(overlap.selected_controls(ignore_first=True), ['|' + second])

    def test_create_reads_current_play_range_and_selection(self):
        from overlap_motion import overlap
        node = self.moving()
        cmds.playbackOptions(minTime=4, maxTime=20)
        layer = overlap.create(rotation=False, axes=('Y',))
        self.assertTrue(layer.startswith('OverlapHelper'))
        self.assertLess(cmds.getAttr(node + '.translateY', time=5), 8)
        # The original layer has constant weight; only the baked keys are ranged.
        self.assertEqual(cmds.getAttr(layer + '.weight', time=3), 1)
        self.assertEqual(cmds.getAttr(layer + '.weight', time=20), 1)
        self.assertEqual(cmds.getAttr(layer + '.weight', time=20.5), 1)
        curves = cmds.animLayer(layer, query=True, animCurves=True)
        times = cmds.keyframe(curves, query=True, timeChange=True)
        self.assertEqual((min(times), max(times)), (4, 20))

    def test_custom_offset_axis_exposes_a_new_rotation_axis(self):
        from overlap_motion import overlap
        node = cmds.createNode('transform', name='control')
        for frame, value in [(1, 0), (4, 0), (5, 8), (31, 8)]:
            cmds.setKeyframe(node, attribute='translateZ', time=frame, value=value)
        cmds.select(node)
        layer = overlap.create(custom=True, physics=True, axes=('X',))
        cmds.currentTime(5)
        self.assertGreater(abs(cmds.getAttr(node + '.rotateY')), 1)
        self.assertLess(abs(cmds.getAttr(node + '.rotateX')), 1e-5)
        self.assertTrue(layer)

    def test_scale_zero_is_rejected_without_changing_scene(self):
        from overlap_motion import overlap
        node = cmds.createNode('transform', name='control')
        for frame, value in [(1, 0), (31, 45)]:
            cmds.setKeyframe(node, attribute='rotateZ', time=frame, value=value,
                             inTangentType='linear', outTangentType='linear')
        expected = cmds.getAttr(node + '.rotateZ', time=15)
        cmds.select(node)
        before = set(cmds.ls())
        with self.assertRaises(ValueError):
            overlap.create(scale=0, custom=True, physics=True)
        self.assertAlmostEqual(cmds.getAttr(node + '.rotateZ', time=15), expected)
        self.assertEqual(set(cmds.ls()), before)

    def test_fractional_scale_does_not_rotate_a_static_unwrapped_pose(self):
        from overlap_motion import overlap
        for angle in (190, 300, 540):
            cmds.file(new=True, force=True)
            node = cmds.createNode('transform', name='control')
            cmds.setAttr(node + '.rotateZ', angle)
            cmds.select(node)
            overlap.create(scale=0.5, custom=True, axes=('Y',))
            actual = cmds.getAttr(node + '.rotateZ', time=15)
            # Maya animation layers may normalize equivalent whole turns.
            self.assertAlmostEqual(abs(math.cos(math.radians(actual - angle) / 2)), 1)

    def test_ignore_first_retains_root_for_two_control_aim_inference(self):
        from overlap_motion import overlap
        root = cmds.createNode('transform', name='root')
        child = cmds.createNode('transform', name='child', parent=root)
        cmds.setAttr(child + '.translateX', 5)
        for frame, value in [(1, 0), (4, 0), (5, 3), (31, 3)]:
            cmds.setKeyframe(root, attribute='translateY', time=frame, value=value)
        cmds.select(root)
        layer = overlap.create(hierarchy=True, ignore_first=True)
        self.assertLess(cmds.getAttr(child + '.rotateZ', time=5), -5)
        self.assertFalse(cmds.listConnections(root + '.rotateZ'))
        self.assertTrue(layer)

    def test_direct_bake_preserves_outside_integer_frames_and_surrounding_segments(self):
        node = cmds.createNode('transform', name='control')
        for frame, value in [(1, 0), (31, 30)]:
            cmds.setKeyframe(node, attribute='translateY', time=frame, value=value,
                             inTangentType='linear', outTangentType='linear')
        outside = [1, 8.5, 9, 21, 21.25, 25, 30]
        before = [cmds.getAttr(node + '.translateY', time=t) for t in outside]
        core.bake([node], 10, 20, mode='soft', delay=0, rotation=False,
                  translation=True, add_to_layer=False)
        after = [cmds.getAttr(node + '.translateY', time=t) for t in outside]
        for expected, actual in zip(before, after):
            self.assertAlmostEqual(actual, expected, places=5)

    def test_normal_rotation_requires_two_controls_in_both_modes(self):
        from overlap_motion import overlap
        for physics in (False, True):
            cmds.file(new=True, force=True)
            cmds.playbackOptions(minTime=1, maxTime=31)
            node = cmds.createNode('transform', name='control')
            for frame, value in [(1, 0), (4, 0), (5, 60), (31, 60)]:
                cmds.setKeyframe(node, attribute='rotateY', time=frame, value=value)
            cmds.select(node)
            before = set(cmds.ls())
            with self.assertRaises(ValueError):
                overlap.create(axes=('Y',), physics=physics)
            self.assertEqual(set(cmds.ls()), before)

    def test_direct_bake_freezes_existing_auto_guard_tangents(self):
        node = cmds.createNode('transform', name='control')
        for frame, value in [(1, 0), (9, 7), (10, 8), (15, -4), (20, 16), (21, 15), (31, 5)]:
            cmds.setKeyframe(node, attribute='translateY', time=frame, value=value,
                             inTangentType='auto', outTangentType='auto')
        outside = [1.5, 8.5, 9, 21, 21.25, 25, 30.5]
        before = [cmds.getAttr(node + '.translateY', time=t) for t in outside]
        core.bake([node], 10, 20, mode='soft', delay=0, rotation=False,
                  translation=True, add_to_layer=False)
        after = [cmds.getAttr(node + '.translateY', time=t) for t in outside]
        for expected, actual in zip(before, after):
            self.assertAlmostEqual(actual, expected, places=5)


if __name__ == '__main__':
    unittest.main()
