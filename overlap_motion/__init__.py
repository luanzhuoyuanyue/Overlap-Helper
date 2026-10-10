"""An independent implementation of the Overlap Helper Overlap page."""

__version__ = '1.2.0'


def show():
    from .ui import show as show_window
    return show_window()
