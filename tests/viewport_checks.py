"""Viewport suspension and recovery in a disposable real Maya GUI."""
import unittest
from unittest import mock

from maya import cmds
from overlap_motion import legacy, overlap
from test_maya2023_parity import reference_scene
from test_stability import RecoveryTests


class ViewportTests(unittest.TestCase):
    def setUp(self):
        if cmds.about(batch=True):
            self.skipTest('Viewport state requires a Maya GUI')
        self.original_pause = cmds.ogs(query=True, pause=True)
        self.set_pause(False)
        reference_scene()
        cmds.playbackOptions(maxTime=9, animationEndTime=9)
        cmds.currentTime(7)
        cmds.autoKeyframe(state=True)
        self.before = RecoveryTests.snapshot()

    def tearDown(self):
        self.set_pause(self.original_pause)

    @staticmethod
    def set_pause(paused):
        if cmds.ogs(query=True, pause=True) != paused:
            cmds.ogs(pause=True)

    def marker(self):
        node = cmds.createNode('transform', name='userMarker')
        cmds.select(self.before['selection'], replace=True)
        cmds.setAttr(node + '.translateX', 9)
        self.before = RecoveryTests.snapshot()
        return node

    def test_baking_pauses_viewport_and_success_resumes_it(self):
        bake_chain = legacy.Overlap.bake_chain

        def check_paused(op, *args, **kwargs):
            self.assertTrue(cmds.ogs(query=True, pause=True))
            return bake_chain(op, *args, **kwargs)

        with mock.patch.object(legacy.Overlap, 'bake_chain', check_paused):
            self.assertTrue(overlap.create())
        self.assertFalse(cmds.ogs(query=True, pause=True))

    def test_previously_paused_viewport_stays_paused(self):
        self.set_pause(True)
        self.assertTrue(overlap.create(physics=True, smoothness=8))
        self.assertTrue(cmds.ogs(query=True, pause=True))

    def test_bake_error_resumes_viewport_and_rolls_back(self):
        def fail(*args, **kwargs):
            self.assertTrue(cmds.ogs(query=True, pause=True))
            raise RuntimeError('bake failed')

        with mock.patch.object(cmds, 'pasteKey', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'bake failed'):
                overlap.create(physics=True, smoothness=8)
        self.assertFalse(cmds.ogs(query=True, pause=True))
        self.assertEqual(RecoveryTests.snapshot(), self.before)

    def test_interruption_resumes_viewport_and_rolls_back(self):
        def interrupt(*args, **kwargs):
            self.assertTrue(cmds.ogs(query=True, pause=True))
            raise KeyboardInterrupt('cancel bake')

        with mock.patch.object(cmds, 'pasteKey', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                overlap.create(add_to_layer=False)
        self.assertFalse(cmds.ogs(query=True, pause=True))
        self.assertEqual(RecoveryTests.snapshot(), self.before)

    def test_resume_failure_recovers_without_consuming_previous_undo(self):
        marker = self.marker()
        ogs = cmds.ogs
        injected = [False]

        def fail_resume_once(*args, **kwargs):
            if not kwargs.get('query') and kwargs.get('pause') and \
                    ogs(query=True, pause=True) and not injected[0]:
                injected[0] = True
                raise RuntimeError('viewport resume failed')
            return ogs(*args, **kwargs)

        with mock.patch.object(cmds, 'ogs', side_effect=fail_resume_once):
            with self.assertRaisesRegex(RuntimeError, 'viewport resume failed'):
                overlap.create()
        self.assertTrue(injected[0])
        self.assertFalse(cmds.ogs(query=True, pause=True))
        self.assertEqual(RecoveryTests.snapshot(), self.before)
        cmds.undo()
        self.assertEqual(cmds.getAttr(marker + '.translateX'), 0)

    def test_pause_failure_preserves_previous_undo(self):
        ogs = cmds.ogs

        def fail_pause(*args, **kwargs):
            if not kwargs.get('query') and kwargs.get('pause'):
                raise RuntimeError('viewport pause failed')
            return ogs(*args, **kwargs)

        for auto in (False, True):
            with self.subTest(auto_key=auto):
                cmds.autoKeyframe(state=auto)
                self.before = RecoveryTests.snapshot()
                marker = self.marker()
                with mock.patch.object(cmds, 'ogs', side_effect=fail_pause):
                    with self.assertRaisesRegex(RuntimeError, 'viewport pause failed'):
                        overlap.create()
                self.assertFalse(cmds.ogs(query=True, pause=True))
                self.assertEqual(RecoveryTests.snapshot(), self.before)
                cmds.undo()
                self.assertEqual(cmds.getAttr(marker + '.translateX'), 0)
