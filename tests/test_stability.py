"""Failure recovery against real Maya scene and application state."""
import unittest
from unittest import mock

from maya import cmds
from overlap_motion import legacy, overlap
from test_maya2023_parity import reference_scene


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        reference_scene()
        cmds.currentTime(7)
        cmds.autoKeyframe(state=True)
        cmds.evaluationManager(mode='parallel')
        self.before = self.snapshot()

    @staticmethod
    def snapshot():
        return {
            'nodes': set(cmds.ls()),
            'curves': {c: (cmds.keyframe(c, query=True, timeChange=True),
                           cmds.keyframe(c, query=True, valueChange=True))
                       for c in cmds.ls(type='animCurve')},
            'time': cmds.currentTime(query=True),
            'auto': cmds.autoKeyframe(query=True, state=True),
            'undo_enabled': cmds.undoInfo(query=True, state=True),
            'mode': cmds.evaluationManager(query=True, mode=True)[0],
            'selection': cmds.ls(selection=True, long=True),
            'range': [cmds.playbackOptions(query=True, **{key: True})
                      for key in ('minTime', 'maxTime', 'animationStartTime', 'animationEndTime')],
        }

    def test_cleanup_failure_rolls_back_completed_bake_and_restores_state(self):
        with mock.patch.object(legacy.Overlap, 'cleanup', side_effect=RuntimeError('cleanup failed')):
            with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
                overlap.create(physics=True, smoothness=8, loop=True)
        self.assertEqual(self.snapshot(), self.before)

    def test_cleanup_failure_preserves_original_bake_error(self):
        with mock.patch.object(cmds, 'pasteKey', side_effect=RuntimeError('bake failed')), \
                mock.patch.object(legacy.Overlap, 'cleanup', side_effect=RuntimeError('cleanup failed')):
            with self.assertRaisesRegex(RuntimeError, 'bake failed'):
                overlap.create(physics=True, smoothness=8, loop=True)
        self.assertEqual(self.snapshot(), self.before)

    def test_one_restore_error_does_not_skip_other_state_and_rolls_back(self):
        current_time = cmds.currentTime
        injected = [False]

        def fail_restore_once(*args, **kwargs):
            if args == (7.0,) and not injected[0]:
                injected[0] = True
                raise RuntimeError('time restore failed')
            return current_time(*args, **kwargs)

        with mock.patch.object(cmds, 'currentTime', side_effect=fail_restore_once):
            with self.assertRaisesRegex(RuntimeError, 'time restore failed'):
                overlap.create(physics=True, smoothness=8, loop=True)
        self.assertTrue(injected[0])
        self.assertEqual(self.snapshot(), self.before)

    def test_interruption_rolls_back_direct_write(self):
        paste = cmds.pasteKey
        calls = [0]

        def interrupt(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 2:
                raise KeyboardInterrupt('cancel bake')
            return paste(*args, **kwargs)

        with mock.patch.object(cmds, 'pasteKey', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                overlap.create(physics=True, smoothness=8, add_to_layer=False)
        self.assertEqual(self.snapshot(), self.before)

    def test_recovery_command_failure_does_not_mask_original_error(self):
        marker = cmds.createNode('transform', name='userMarker')
        cmds.select(self.before['selection'], replace=True)
        cmds.setAttr(marker + '.translateX', 9)
        self.before = self.snapshot()
        undo_info = cmds.undoInfo
        injected = [False]

        def fail_recording_once(*args, **kwargs):
            if kwargs.get('stateWithoutFlush') is False and not injected[0]:
                injected[0] = True
                raise RuntimeError('recording suspend failed')
            return undo_info(*args, **kwargs)

        with mock.patch.object(cmds, 'pasteKey', side_effect=RuntimeError('bake failed')), \
                mock.patch.object(cmds, 'undoInfo', side_effect=fail_recording_once):
            with self.assertRaisesRegex(RuntimeError, 'bake failed'):
                overlap.create(physics=True, smoothness=8, loop=True)
        self.assertTrue(injected[0])
        self.assertEqual(self.snapshot(), self.before)
        cmds.undo()
        self.assertEqual(cmds.getAttr(marker + '.translateX'), 0)

    def test_failure_preserves_previous_undo_entry(self):
        marker = cmds.createNode('transform', name='userMarker')
        cmds.select(self.before['selection'], replace=True)
        cmds.setAttr(marker + '.translateX', 9)
        self.before = self.snapshot()
        with mock.patch.object(cmds, 'pasteKey', side_effect=RuntimeError('bake failed')):
            with self.assertRaisesRegex(RuntimeError, 'bake failed'):
                overlap.create(physics=True, smoothness=8)
        self.assertEqual(self.snapshot(), self.before)
        cmds.undo()
        self.assertTrue(cmds.objExists(marker))
        self.assertEqual(cmds.getAttr(marker + '.translateX'), 0)

    def test_close_chunk_failure_rolls_back_without_consuming_user_undo(self):
        marker = cmds.createNode('transform', name='userMarker')
        cmds.select(self.before['selection'], replace=True)
        cmds.setAttr(marker + '.translateX', 9)
        self.before = self.snapshot()
        undo_info = cmds.undoInfo
        injected = [False]

        def fail_close_once(*args, **kwargs):
            if kwargs.get('closeChunk') and not injected[0]:
                injected[0] = True
                raise RuntimeError('close chunk failed')
            return undo_info(*args, **kwargs)

        with mock.patch.object(cmds, 'undoInfo', side_effect=fail_close_once):
            with self.assertRaisesRegex(RuntimeError, 'close chunk failed'):
                overlap.create(physics=True, smoothness=8)
        self.assertTrue(injected[0])
        self.assertEqual(self.snapshot(), self.before)
        cmds.undo()
        self.assertTrue(cmds.objExists(marker))
        self.assertEqual(cmds.getAttr(marker + '.translateX'), 0)


if __name__ == '__main__':
    unittest.main()
