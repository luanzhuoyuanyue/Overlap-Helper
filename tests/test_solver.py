import math
import unittest

from overlap_motion.solver import solve, rotate


IDENTITY = (0.0, 0.0, 0.0, 1.0)


class SolverTests(unittest.TestCase):
    def run_solver(self, positions, **options):
        defaults = dict(delay=0.0, mode='spring', response=12.0,
                        damping=0.3, strength=1.0, axis=(1, 0, 0),
                        length=5.0, cycle=False)
        defaults.update(options)
        rotations = defaults.pop('rotations', [IDENTITY] * len(positions))
        return solve(positions, rotations, **defaults)

    def test_fractional_delay_interpolates_and_holds_start(self):
        points, _ = self.run_solver([(i * 10.0, 0, 0) for i in range(4)],
                                    mode='delay', delay=1.5)
        self.assertEqual([p[0] for p in points], [0, 0, 5, 15])

    def test_rest_pose_does_not_drift(self):
        points, quats = self.run_solver([(3, 5, -2)] * 80)
        for p, q in zip(points, quats):
            for actual, expected in zip(p, (3, 5, -2)):
                self.assertAlmostEqual(actual, expected)
            self.assertAlmostEqual(abs(q[3]), 1.0)

    def test_spring_overshoots_then_settles(self):
        points, _ = self.run_solver([(0, 0, 0)] * 3 + [(10, 0, 0)] * 90)
        values = [p[0] for p in points]
        self.assertGreater(values[3], 0)
        self.assertLess(values[3], 10)
        self.assertGreater(max(values), 10.5)
        self.assertAlmostEqual(values[-1], 10, places=4)

    def test_non_physics_softness_has_lag_without_overshoot(self):
        source = [(0, 0, 0)] * 3 + [(10, 0, 0)] * 150
        soft, _ = self.run_solver(source, mode='soft', response=12)
        stiff, _ = self.run_solver(source, mode='soft', response=3)
        self.assertLess(soft[3][0], stiff[3][0])
        self.assertTrue(all(0 <= p[0] <= 10 for p in soft))
        self.assertAlmostEqual(soft[-1][0], 10, places=3)

    def test_translation_can_excite_rotational_swing(self):
        _, quats = self.run_solver([(0, 0, 0)] * 3 + [(0, 3, 0)] * 30)
        axis = rotate(quats[3], (1, 0, 0))
        self.assertLess(axis[1], -0.1)
        self.assertGreater(axis[0], 0.5)

    def test_zero_strength_preserves_source(self):
        source = [(0, 0, 0), (5, 2, 0), (0, 0, 0)]
        points, quats = self.run_solver(source, strength=0)
        self.assertEqual(points, source)
        self.assertEqual(quats, [IDENTITY] * 3)

    def test_rotation_delay_uses_short_arc_across_antipodes(self):
        q = (0, 0, math.sin(math.pi / 4), math.cos(math.pi / 4))
        _, result = self.run_solver([(0, 0, 0)] * 3, mode='delay', delay=0.5,
                                    rotations=[q, tuple(-x for x in q), q])
        for rotation in result:
            v = rotate(rotation, (1, 0, 0))
            self.assertAlmostEqual(v[0], 0, places=6)
            self.assertAlmostEqual(v[1], 1, places=6)

    def test_loop_is_periodic_at_seam_and_has_no_startup_transient(self):
        points = [(0, math.sin(i * 2 * math.pi / 40), 0) for i in range(41)]
        result, rotations = self.run_solver(points, cycle=True)
        self.assertEqual(result[0], result[-1])
        self.assertEqual(rotations[0], rotations[-1])
        self.assertGreater(abs(result[0][1]), 0.02)
        incoming = result[-1][1] - result[-2][1]
        outgoing = result[1][1] - result[0][1]
        self.assertLess(abs(incoming - outgoing), 0.04)

    def test_short_loop_and_soft_spring_remain_finite(self):
        result, rotations = self.run_solver([(0, 0, 0), (0, 10, 0), (0, 0, 0)],
                                            cycle=True, response=120, damping=0.05)
        self.assertTrue(all(math.isfinite(v) for p in result + rotations for v in p))
        self.assertEqual(result[0], result[-1])


if __name__ == '__main__':
    unittest.main()
