"""Run with mayapy; every integration test uses its own unsaved new scene."""
import os
import sys
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ['MAYA_SKIP_USERSETUP_PY'] = '1'
os.environ['PYTHONIOENCODING'] = 'utf-8'

import maya.standalone

maya.standalone.initialize(name='python')
try:
    if len(sys.argv) > 1:
        sys.path.insert(0, str(root / 'tests'))
        suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
    else:
        suite = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
finally:
    maya.standalone.uninitialize()
sys.exit(0 if result.wasSuccessful() else 1)
