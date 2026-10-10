"""Golden outputs recorded from the shipped encrypted plugin in Maya 2023.3.

These tests catch replacing its frame offsets / nParticle goals with generic
filters, changing constraint offsets, or baking a different selection order.
"""
import json
import unittest
from unittest import mock
from pathlib import Path

from maya import cmds
from overlap_motion import overlap


def reference_scene():
    cmds.file(new=True, force=True)
    cmds.undoInfo(state=True)
    cmds.autoKeyframe(state=False)
    cmds.currentUnit(time='film', angle='deg', linear='cm')
    cmds.playbackOptions(minTime=1, maxTime=41, animationStartTime=1, animationEndTime=41)
    cmds.select(clear=True)
    nodes = [cmds.joint(name='control%d' % i, position=(0, i * 5, 0)) for i in range(4)]
    for attr, values in [('translateX', [(1, 0), (11, 7), (21, 0), (31, -7), (41, 0)]),
                         ('rotateZ', [(1, 0), (11, 35), (21, 0), (31, -35), (41, 0)]),
                         ('rotateY', [(1, 0), (11, 40), (21, 0), (31, -40), (41, 0)])]:
        for frame, value in values:
            cmds.setKeyframe(nodes[0], attribute=attr, time=frame, value=value,
                             inTangentType='linear', outTangentType='linear')
    cmds.currentTime(1)
    cmds.select(nodes)
    return nodes


def extra_scene(kind):
    nodes = reference_scene()
    if kind == 'locked-axis':
        cmds.setAttr(nodes[1] + '.rotateX', lock=True)
    if kind == 'two-chains':
        cmds.select(clear=True)
        other = [cmds.joint(name='other%d' % i, position=(20, i * 5, 0)) for i in range(4)]
        for frame, value in [(1, 0), (11, 30), (21, 0), (31, -30), (41, 0)]:
            cmds.setKeyframe(other[0], attribute='rotateX', time=frame, value=value,
                             inTangentType='linear', outTangentType='linear')
        nodes += other
        cmds.select(nodes[0], nodes[4])
    elif kind == 'custom-multi':
        cmds.select(nodes[1])
        nodes = [nodes[1]]
    else:
        cmds.select(nodes)
    cmds.currentTime(1)
    return nodes


class Maya2023ParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads((Path(__file__).parent / 'fixtures' /
                                    'maya2023-original.json').read_text(encoding='utf-8'))
        cls.extended = json.loads((Path(__file__).parent / 'fixtures' /
                                  'maya2023-extended.json').read_text(encoding='utf-8'))
        cls.extra = json.loads((Path(__file__).parent / 'fixtures' /
                               'maya2023-extra.json').read_text(encoding='utf-8'))
        cls.metrics = []

    @classmethod
    def tearDownClass(cls):
        if not cls.metrics:
            return
        qa = Path(__file__).parents[1] / 'qa'
        qa.mkdir(exist_ok=True)
        (qa / ('parity-%s.json' % cmds.about(version=True))).write_text(json.dumps({
            'maya': cmds.about(version=True), 'original': 'Maya 2023.3 encrypted original',
            'tolerance': 1e-4, 'cases': cls.metrics,
            'maximum_translate_error_cm': max(c['translation_error_cm'] for c in cls.metrics),
            'maximum_rotate_error_degrees': max(c['rotation_error_degrees'] for c in cls.metrics)
        }, indent=2), encoding='utf-8')

    def compare_frames(self, name, nodes, frames):
        translation_errors, rotation_errors = [], []
        for frame, controls in enumerate(frames, 1):
            cmds.currentTime(frame)
            for node, expected in zip(nodes, controls):
                actual = list(cmds.getAttr(node+'.translate')[0]) + list(cmds.getAttr(node+'.rotate')[0])
                translation_errors.extend(abs(a-b) for a,b in zip(actual[:3],expected[:3]))
                rotation_errors.extend(abs(a-b) for a,b in zip(actual[3:],expected[3:]))
        self.metrics.append({'case': name, 'frames': len(frames), 'controls': len(nodes),
                             'translation_error_cm': max(translation_errors),
                             'rotation_error_degrees': max(rotation_errors)})
        error = max(translation_errors + rotation_errors)
        self.assertLess(error, 1e-4, '%s maximum channel error: %.9g' % (name,error))

    def test_original_locked_multi_axis_and_separate_hierarchies(self):
        for name, fixture in self.extra.items():
            with self.subTest(case=name):
                nodes = extra_scene(name)
                overlap.create(**fixture['options'])
                self.compare_frames(name, nodes, fixture['after'])
                layers = [l for l in cmds.ls(type='animLayer') if l != 'BaseAnimation']
                self.assertEqual(len(layers), fixture['layer_count'])
                if name == 'locked-axis':
                    self.assertTrue(cmds.getAttr(nodes[1]+'.rotateX',lock=True))

    def check_case(self, rotation, physics):
        nodes = reference_scene()
        case = ('physics' if physics else 'offset') + ('-rotation' if rotation else '-translation')
        layer = overlap.create(rotation=rotation, physics=physics,
                               smoothness=8.0 if physics else 3.0)
        self.assertTrue(layer and cmds.objExists(layer))
        self.compare_frames(case, nodes, self.reference[case])

    def test_original_offset_rotation(self):
        self.check_case(True, False)

    def test_original_offset_translation(self):
        self.check_case(False, False)

    def test_original_particle_rotation(self):
        self.check_case(True, True)

    def test_original_particle_translation(self):
        self.check_case(False, True)

    def test_original_extended_modes(self):
        for name, fixture in self.extended.items():
            with self.subTest(case=name):
                nodes = reference_scene()
                options = fixture['options']
                if options.get('custom'):
                    cmds.select(nodes[1])
                    nodes = [nodes[1]]
                if options.get('loop'):
                    for curve in cmds.ls(type='animCurve'):
                        cmds.setInfinity(curve, preInfinite='cycle', postInfinite='cycle')
                cmds.currentTime(1)
                layer = overlap.create(**options)
                self.compare_frames(name, nodes, fixture['after'])
                self.assertEqual(bool(layer), options.get('add_to_layer', True))
                self.assertEqual([cmds.playbackOptions(q=True, min=True),
                                  cmds.playbackOptions(q=True, max=True)], fixture['range'])

    def test_particle_bake_preserves_existing_user_solver(self):
        nodes = reference_scene()
        particle, shape = cmds.nParticle(position=[(30, 0, 0)], name='userParticle')
        nucleus = cmds.listConnections(shape, type='nucleus')[0]
        cmds.setAttr(nucleus + '.timeScale', 0.77)
        time_scale = cmds.getAttr(nucleus + '.timeScale')
        before = set(cmds.listConnections(nucleus, connections=True, plugs=True) or [])
        cmds.select(nodes)
        overlap.create(physics=True, smoothness=8)
        self.assertTrue(cmds.objExists(particle) and cmds.objExists(nucleus))
        self.assertEqual(cmds.getAttr(nucleus + '.timeScale'), time_scale)
        self.assertEqual(set(cmds.listConnections(nucleus, connections=True, plugs=True) or []), before)
        self.assertFalse(cmds.ls('overlapHelperTemp_*'))

    def test_direct_write_failure_restores_original_scene(self):
        for physics in (False, True):
            with self.subTest(physics=physics):
                nodes = reference_scene()
                before_nodes = set(cmds.ls())
                curves = {c: (cmds.keyframe(c, query=True, timeChange=True),
                               cmds.keyframe(c, query=True, valueChange=True))
                          for c in cmds.ls(type='animCurve')}
                before_selection = cmds.ls(selection=True, long=True)
                before_mode = cmds.evaluationManager(query=True, mode=True)
                paste = cmds.pasteKey
                calls = [0]
                def fail_after_first(*args, **kwargs):
                    calls[0] += 1
                    if calls[0] == 2:
                        raise RuntimeError('injected paste failure')
                    return paste(*args, **kwargs)
                with mock.patch.object(cmds, 'pasteKey', side_effect=fail_after_first):
                    with self.assertRaisesRegex(RuntimeError, 'injected paste failure'):
                        overlap.create(physics=physics, smoothness=8 if physics else 3, add_to_layer=False)
                self.assertEqual(set(cmds.ls()), before_nodes)
                self.assertEqual(cmds.ls(selection=True,long=True), before_selection)
                self.assertEqual(cmds.evaluationManager(query=True,mode=True), before_mode)
                for curve, (times, values) in curves.items():
                    self.assertEqual(cmds.keyframe(curve,query=True,timeChange=True), times)
                    self.assertEqual(cmds.keyframe(curve,query=True,valueChange=True), values)

    def test_rotation_preserves_translation_constraint_driver(self):
        nodes = reference_scene()
        cmds.cutKey(nodes[0],attribute='translateX',clear=True)
        driver = cmds.createNode('transform',name='translationDriver')
        for frame,value in [(1,0),(11,7),(21,0),(31,-7),(41,0)]:
            cmds.setKeyframe(driver,attribute='translateX',time=frame,value=value)
        cmds.pointConstraint(driver,nodes[0],maintainOffset=True)
        before_connections = cmds.listConnections(nodes[0]+'.translateX',source=True,destination=False,plugs=True)
        before = [cmds.getAttr(nodes[0]+'.translateX',time=f) for f in range(1,42)]
        cmds.currentTime(1)
        cmds.select(nodes)
        overlap.create()
        self.assertEqual(cmds.listConnections(nodes[0]+'.translateX',source=True,destination=False,plugs=True),before_connections)
        self.assertEqual([cmds.getAttr(nodes[0]+'.translateX',time=f) for f in range(1,42)],before)
        self.assertFalse(cmds.ls(type='pairBlend'))

    def test_particle_bake_one_undo_restores_source(self):
        nodes = reference_scene()
        before = set(cmds.ls())
        evaluation_mode = cmds.evaluationManager(query=True, mode=True)
        cmds.currentTime(7)
        cmds.autoKeyframe(state=True)
        layer = overlap.create(physics=True, smoothness=8)
        self.assertEqual(cmds.currentTime(query=True), 7)
        self.assertTrue(cmds.autoKeyframe(query=True, state=True))
        self.assertEqual(cmds.evaluationManager(query=True, mode=True), evaluation_mode)
        self.assertFalse(cmds.ls('overlapHelperTemp_*'))
        cmds.undo()
        self.assertFalse(cmds.objExists(layer))
        self.assertEqual(set(cmds.ls()), before)
