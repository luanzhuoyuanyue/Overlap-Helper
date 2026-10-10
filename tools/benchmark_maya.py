"""Compare two revisions in fresh, disposable Maya scenes.

Run with mayapy: tools/benchmark_maya.py --baseline PATH --output qa/performance-2027.json
The timer includes only create(); startup, scene setup and output checks are excluded.
"""
import argparse
import importlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time


def load_revision(root, name):
    spec = importlib.util.spec_from_file_location(
        name, Path(root) / 'overlap_motion' / '__init__.py',
        submodule_search_locations=[str(Path(root) / 'overlap_motion')])
    package = importlib.util.module_from_spec(spec)
    sys.modules[name] = package
    spec.loader.exec_module(package)
    return importlib.import_module(name + '.overlap')


def scene(count, frames, bent):
    from maya import cmds
    cmds.file(new=True, force=True)
    cmds.undoInfo(state=True)
    cmds.autoKeyframe(state=False)
    cmds.evaluationManager(mode='parallel')
    cmds.currentUnit(time='film', angle='deg', linear='cm')
    cmds.playbackOptions(minTime=1, maxTime=frames,
                         animationStartTime=1, animationEndTime=frames)
    cmds.select(clear=True)
    nodes = [cmds.joint(name='bench%d' % i, position=(i % 3 if bent else 0, i * 5,
                                                   i % 2 if bent else 0)) for i in range(count)]
    if bent:
        for i, node in enumerate(nodes):
            cmds.setAttr(node + '.rotateOrder', i % 6)
            cmds.setAttr(node + '.jointOrient', 3 * (i % 3), 5 * (i % 2), 0)
    for attr, amount in [('translateX', 7), ('rotateY', 40), ('rotateZ', 35)]:
        for fraction, value in [(0, 0), (0.25, amount), (0.5, 0), (0.75, -amount), (1, 0)]:
            cmds.setKeyframe(nodes[0], attribute=attr, time=1 + fraction * (frames - 1),
                             value=value, inTangentType='linear', outTangentType='linear')
    cmds.currentTime(1)
    cmds.select(nodes)
    return nodes


def sample(nodes, frames):
    from maya import cmds
    values = []
    for frame in range(1, frames + 1):
        cmds.currentTime(frame)
        values.append([list(cmds.getAttr(node + '.translate')[0]) +
                       list(cmds.getAttr(node + '.rotate')[0]) for node in nodes])
    return values


def maximum_error(first, second):
    return max(abs(a - b) for f1, f2 in zip(first, second)
               for n1, n2 in zip(f1, f2) for a, b in zip(n1, n2))


def benchmark(baseline, output, count=24, frames=121, repeats=3, bent=False, cases=None):
    from maya import cmds
    revisions = {'baseline': load_revision(baseline, 'overlap_baseline'),
                 'optimized': load_revision(Path(__file__).resolve().parents[1], 'overlap_optimized')}
    # Warm command initialization before timed runs.
    for revision in revisions.values():
        scene(4, 41, bent)
        revision.create()
    report = {'maya': cmds.about(version=True), 'batch': cmds.about(batch=True),
              'controls': count, 'frames': frames, 'repeats': repeats, 'bent_chain': bent,
              'evaluation_mode': 'parallel (physics temporarily uses DG)',
              'timer': 'create only; setup/startup/sampling excluded', 'cases': []}
    for rotation, physics in [(True, False), (False, False), (True, True), (False, True)]:
        name = ('physics' if physics else 'offset') + ('-rotation' if rotation else '-translation')
        if cases and name not in cases:
            continue
        timings = {label: [] for label in revisions}
        reference = None
        error = 0.0
        for repeat in range(repeats):
            labels = list(revisions) if repeat % 2 == 0 else list(reversed(revisions))
            for label in labels:
                nodes = scene(count, frames, bent)
                began = time.perf_counter()
                revisions[label].create(rotation=rotation, physics=physics,
                                        smoothness=8 if physics else 3)
                elapsed = time.perf_counter() - began
                timings[label].append(elapsed)
                values = sample(nodes, frames)
                if reference is None:
                    reference = values
                error = max(error, maximum_error(reference, values))
                print('%s %s run %d: %.4f s' % (name, label, repeat + 1, elapsed), flush=True)
        medians = {label: statistics.median(times) for label, times in timings.items()}
        result = {'case': name, 'seconds': timings, 'median_seconds': medians,
                  'speedup': medians['baseline'] / medians['optimized'],
                  'maximum_channel_error': error, 'checked_runs': 2 * repeats}
        report['cases'].append(result)
        Path(output).write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(result), flush=True)
        if error >= 1e-4:
            raise AssertionError('Motion changed: ' + name)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--controls', type=int, default=24)
    parser.add_argument('--frames', type=int, default=121)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--bent', action='store_true')
    parser.add_argument('--cases', nargs='+')
    args = parser.parse_args()
    import os
    os.environ['MAYA_SKIP_USERSETUP_PY'] = '1'
    import maya.standalone
    maya.standalone.initialize(name='python')
    try:
        benchmark(args.baseline, args.output, args.controls, args.frames,
                  args.repeats, args.bent, args.cases)
    finally:
        maya.standalone.uninitialize()
