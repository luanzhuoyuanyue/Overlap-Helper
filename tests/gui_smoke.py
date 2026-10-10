"""Run in a disposable Maya GUI/profile; never in a user's working scene."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import traceback
import unittest

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa'
QA.mkdir(exist_ok=True)
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from maya import cmds, utils
from PySide6 import QtCore, QtWidgets


def run():
    version = cmds.about(version=True)
    report = {'maya': version, 'passed': False, 'checks': []}
    try:
        suite = unittest.defaultTestLoader.loadTestsFromNames(['ui_checks', 'test_maya2023_parity'])
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        report['tests'] = stream.getvalue()
        assert result.wasSuccessful(), stream.getvalue()
        report['checks'].append('2023 UI states, 23 golden motion cases, undo and existing dynamics')
        from overlap_motion import ui
        from test_maya2023_parity import reference_scene, Maya2023ParityTests
        for rotation in (True, False):
            for physics in (False, True):
                nodes = reference_scene()
                window = ui.show()
                if not rotation:
                    window.trans.click()
                if physics:
                    window.physics.click()
                window.create_button.click()
                assert window.last_layer and window.last_error is None, window.last_error
                case = ('physics' if physics else 'offset') + ('-rotation' if rotation else '-translation')
                for frame, controls in enumerate(Maya2023ParityTests.reference[case], 1):
                    cmds.currentTime(frame)
                    for node, expected in zip(nodes, controls):
                        actual = list(cmds.getAttr(node + '.translate')[0]) + list(cmds.getAttr(node + '.rotate')[0])
                        assert max(abs(a-b) for a,b in zip(actual,expected)) < 1e-4, case
        report['checks'].append('real Create button matches all four original mode trajectories')
        spec = importlib.util.spec_from_file_location('om_installer', ROOT / 'install.py')
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        installer.onMayaDroppedPythonFile()
        installer.onMayaDroppedPythonFile()
        from maya import mel
        import overlap_motion
        from overlap_motion import ui
        shelf = cmds.tabLayout(mel.eval('$testShelf=$gShelfTopLevel'), query=True, selectTab=True)
        buttons = [child for child in cmds.shelfLayout(shelf, query=True, childArray=True) or []
                   if cmds.objectTypeUI(child) == 'shelfButton'
                   and cmds.shelfButton(child, query=True, docTag=True) == 'OverlapMotion']
        assert len(buttons) == 1, buttons
        scripts = Path(cmds.internalVar(userScriptDir=True))
        assert list(scripts.glob('overlap_motion.backup-*'))
        assert Path(overlap_motion.__file__).parent == scripts / 'overlap_motion'
        window = ui._window
        visible = [w for w in QtWidgets.QApplication.topLevelWidgets()
                   if w.objectName() == ui.WINDOW and w.isVisible()]
        assert len(visible) == 1
        report['checks'].append('repeat install, backup, one shelf button, one installed window')
        report.update(passed=True, installed_path=str(scripts / 'overlap_motion'), shelf_buttons=len(buttons))

        def finish():
            if not window.grab().save(str(QA / ('maya%s-ui.png' % version))):
                report.update(passed=False, error='UI screenshot could not be saved')
            (QA / ('gui-result-%s.json' % version)).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            cmds.quit(force=True)
        QtCore.QTimer.singleShot(1200, finish)
    except Exception:
        report['error'] = traceback.format_exc()
        (QA / ('gui-result-%s.json' % version)).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        cmds.quit(force=True)


utils.executeDeferred(run)
