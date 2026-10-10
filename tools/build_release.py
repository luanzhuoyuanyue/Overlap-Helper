"""Build a portable install ZIP from the current source and QA evidence."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
import re
version = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", (ROOT/'overlap_motion'/'__init__.py').read_text()).group(1)
assert (ROOT / 'overlap_motion' / '__init__.py').read_text().find("'" + version + "'") >= 0
paths = [ROOT/'install.py', ROOT/'README.md', ROOT/'使用说明.md', ROOT/'验收报告.md', ROOT/'release-notes.md', ROOT/'docs'/'overlap-reference.md']
for folder in ('overlap_motion', 'tests', 'qa', 'tools'):
    paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file()
                 and '__pycache__' not in p.parts and p.suffix != '.pyc'
                 and p.name not in ('run_gui.mel', 'release-manifest.json'))
output = ROOT/'dist'
output.mkdir(exist_ok=True)
archive = output/('OverlapHelper_Overlap_Maya2025-2027_v%s.zip' % version)
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as target:
    for path in sorted(set(paths)):
        target.write(path, 'OverlapHelper_Overlap/' + path.relative_to(ROOT).as_posix())
with zipfile.ZipFile(archive) as target:
    assert target.testzip() is None
print(archive)
