import importlib.util
from pathlib import Path
import tempfile
import unittest


class InstallTests(unittest.TestCase):
    def test_update_preserves_existing_package_as_backup(self):
        spec = importlib.util.spec_from_file_location('overlap_installer',
                                                     Path(__file__).parents[1] / 'install.py')
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        scratch = Path(__file__).resolve().parents[1] / 'qa'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='overlap-install-test-', dir=scratch) as directory:
            root = Path(directory)
            source, destination = root / 'source', root / 'scripts' / 'overlap_motion'
            source.mkdir()
            (source / '__init__.py').write_text('version = 1', encoding='utf-8')
            self.assertIsNone(installer.copy_package(source, destination))
            self.assertEqual((destination / '__init__.py').read_text(), 'version = 1')
            (destination / 'personal.py').write_text('keep me', encoding='utf-8')
            (source / '__init__.py').write_text('version = 2', encoding='utf-8')
            backup = installer.copy_package(source, destination)
            self.assertEqual((backup / '__init__.py').read_text(), 'version = 1')
            self.assertEqual((backup / 'personal.py').read_text(), 'keep me')
            self.assertEqual((destination / '__init__.py').read_text(), 'version = 2')
            self.assertFalse((destination / 'personal.py').exists())


if __name__ == '__main__':
    unittest.main()
