"""Drag this file into Maya's viewport after extracting the entire ZIP."""

from datetime import datetime
import importlib
from pathlib import Path
import shutil
import sys
import tempfile


def copy_package(source, destination):
    """Install atomically; preserve the entire previous package in a backup."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        return None
    if not (source / '__init__.py').is_file():
        raise ValueError('请先解压完整 ZIP，保留 install.py 旁的 overlap_motion 文件夹。')
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    with tempfile.TemporaryDirectory(prefix='.overlap-motion-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'overlap_motion'
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        if destination.exists():
            backup = destination.with_name(destination.name + '.backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            destination.rename(backup)
        try:
            staged.rename(destination)
        except Exception:
            if backup is not None and not destination.exists():
                backup.rename(destination)
            raise
    return backup


def install():
    from maya import cmds, mel
    scripts = Path(cmds.internalVar(userScriptDir=True))
    backup = copy_package(Path(__file__).resolve().parent / 'overlap_motion',
                          scripts / 'overlap_motion')
    scripts_text = str(scripts)
    if scripts_text in sys.path:
        sys.path.remove(scripts_text)
    sys.path.insert(0, scripts_text)
    old_window = getattr(sys.modules.get('overlap_motion.ui'), '_window', None)
    if old_window is not None:
        try:
            old_window.close()
        except RuntimeError:
            pass
    for name in list(sys.modules):
        if name == 'overlap_motion' or name.startswith('overlap_motion.'):
            del sys.modules[name]
    importlib.invalidate_caches()
    shelf_top = mel.eval('$omShelf = $gShelfTopLevel')
    shelf = cmds.tabLayout(shelf_top, query=True, selectTab=True)
    command = 'import overlap_motion\noverlap_motion.show()'
    existing = None
    for child in cmds.shelfLayout(shelf, query=True, childArray=True) or []:
        if cmds.objectTypeUI(child) == 'shelfButton' and cmds.shelfButton(child, query=True, docTag=True) == 'OverlapMotion':
            existing = child
            break
    options = dict(label='Overlap Helper', annotation='Overlap Helper | Overlap 页独立重写版',
                   image='pythonFamily.png', imageOverlayLabel='OH', sourceType='python',
                   command=command, docTag='OverlapMotion')
    if existing:
        cmds.shelfButton(existing, edit=True, **options)
    else:
        cmds.shelfButton(parent=shelf, **options)
    import overlap_motion
    overlap_motion.show()
    message = 'Overlap Helper 安装完成，工具架按钮为 OH。'
    if backup:
        message += '\n旧版本备份：' + str(backup)
    print(message)
    cmds.inViewMessage(amg='Overlap Helper 安装完成 · 工具架 OH', pos='topCenter', fade=True)


def onMayaDroppedPythonFile(*_):
    install()


if __name__ == '__main__':
    install()
