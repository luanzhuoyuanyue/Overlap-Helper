"""UI contracts observed in the actual Maya 2023 Overlap Helper window."""
import unittest

from PySide6 import QtWidgets
from overlap_motion import ui


class OriginalUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.window = ui.Window()

    def tearDown(self):
        self.window.close()

    def test_physics_resets_smoothness_and_keeps_ignore_first_enabled(self):
        w = self.window
        w.physics.click()
        self.assertEqual(w.smoothness.value(), 8)
        self.assertEqual(w.smoothness.field.minimum(), 2)
        self.assertEqual(w.smoothness.field.maximum(), 9)
        self.assertTrue(w.ignore_first.isEnabled())
        w.physics.click()
        self.assertEqual(w.smoothness.value(), 3)
        self.assertEqual(w.smoothness.field.minimum(), 0.1)
        self.assertEqual(w.smoothness.slider.maximum(), 6000)

    def test_custom_defaults_to_y_and_preserves_multiple_checks(self):
        w = self.window
        w.cus.click()
        self.assertEqual([a for a, b in w.axes.items() if b.isChecked()], ['Y'])
        self.assertFalse(w.ignore_first.isEnabled())
        w.axes['X'].click()
        w.axes['Z'].click()
        self.assertTrue(all(b.isChecked() for b in w.axes.values()))
        w.cus.click()
        self.assertTrue(all(b.isChecked() for b in w.axes.values()))

    def test_translation_resets_axes_and_disables_custom_scale_ignore(self):
        w = self.window
        w.axes['X'].setChecked(False)
        w.trans.click()
        self.assertTrue(all(b.isChecked() for b in w.axes.values()))
        self.assertFalse(w.cus.isEnabled())
        self.assertFalse(w.scale.isEnabled())
        self.assertFalse(w.ignore_first.isEnabled())

    def test_typed_scale_extends_slider_and_original_minimums(self):
        w = self.window
        self.assertEqual(w.scale.field.minimum(), 0.1)
        self.assertEqual(w.overshoot.field.minimum(), 1)
        w.scale.field.setValue(12)
        self.assertEqual(w.scale.value(), 12)
        self.assertEqual(w.scale.slider.maximum(), 12000)
        self.assertEqual(w.scale.slider.value(), 12000)


if __name__ == '__main__':
    unittest.main()
