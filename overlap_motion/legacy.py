"""Maya constraint / nParticle workflow characterized against Maya 2023.3."""
from maya import cmds


class Overlap:
    def __init__(self, start, end, rotation, physics, smoothness, scale, overshoot,
                 axes, add_to_layer, ignore_first=False):
        self.start, self.end = start, end
        self.rotation, self.physics = rotation, physics
        self.delay = smoothness
        self.time_scale = round(1.1 - smoothness / 10.0, 3)
        self.scale, self.overshoot = scale, overshoot
        self.axes, self.add_to_layer = axes, add_to_layer
        self.ignore_first = ignore_first
        self.temporary = []
        self.layer = None

    def locator(self, role):
        node = cmds.spaceLocator(name='overlapHelperTemp_' + role + '#')[0]
        self.temporary.append(node)
        return node

    def chain(self, nodes):
        locs = [self.locator('chain') for _ in range(len(nodes) + 1)]
        cmds.setAttr(locs[0] + '.visibility', False)
        for i in range(len(nodes)):
            cmds.parent(locs[i + 1:], locs[i])
        for i, node in enumerate(nodes):
            cmds.matchTransform(locs[i], node, position=True)
            if i + 1 < len(nodes):
                cmds.aimConstraint(nodes[i + 1], locs[i], weight=1,
                                   aimVector=(0, 1, 0), upVector=(0, 1, 0),
                                   worldUpType='vector', worldUpVector=(0, 0, 1))
                cmds.delete(locs[i], constraints=True)
        spacing = sum(cmds.getAttr(n + '.translateY') for n in locs[1:-1]) / len(nodes)
        cmds.setAttr(locs[-1] + '.translateY', spacing)
        for node, loc in zip(nodes, locs):
            cmds.parentConstraint(node, loc, maintainOffset=True)
        return locs, spacing

    def driver(self, loc, spacing, control):
        cmds.currentTime(self.start)
        goal = self.locator('goal')
        cmds.setAttr(goal + '.visibility', False)
        cmds.matchTransform(goal, loc, position=True, rotation=True)
        cmds.move(0, spacing / self.scale * 5, 0, goal,
                  relative=True, objectSpace=True, localSpace=True)
        cmds.parentConstraint(loc, goal, maintainOffset=True)
        if self.physics:
            # nParticle() creates a non-undoable implicit solver. Build both
            # nodes explicitly, preserving the original one-particle motion.
            nucleus = cmds.createNode('nucleus', name='overlapHelperTemp_nucleus#')
            self.temporary.append(nucleus)
            cmds.connectAttr('time1.outTime', nucleus + '.currentTime')
            cmds.setAttr(nucleus + '.startFrame', self.start)
            if cmds.upAxis(query=True, axis=True) == 'z':
                cmds.setAttr(nucleus + '.gravityDirection', 0, 0, -1)
            particle = cmds.createNode('transform', name='overlapHelperTemp_particle#')
            self.temporary.append(particle)
            shape = cmds.createNode('nParticle', name=particle + 'Shape', parent=particle)
            cmds.connectAttr(shape + '.currentState', nucleus + '.inputActive[0]')
            cmds.connectAttr(shape + '.startState', nucleus + '.inputActiveStart[0]')
            cmds.connectAttr(nucleus + '.outputObjects[0]', shape + '.nextState')
            cmds.connectAttr(nucleus + '.startFrame', shape + '.startFrame')
            cmds.connectAttr('time1.outTime', shape + '.currentTime')
            cmds.setAttr(shape + '.collisionFlag', 1)
            cmds.setAttr(shape + '.selfCollide', False)
            cmds.emit(object=shape, position=cmds.getAttr(goal + '.translate')[0])
            cmds.saveInitialState(particle)
            cmds.goal(particle, weight=0.5, useTransformAsGoal=True, goal=goal)
            driver = self.locator('particleDriver')
            cmds.connectAttr(particle + '.center', driver + '.translate', force=True)
            cmds.setAttr(nucleus + '.timeScale', self.time_scale)
            cmds.setAttr(shape + '.goalSmoothness', self.overshoot)
            cmds.setAttr(shape + '.goalWeight[0]', 0.9)
            return driver, [goal, driver, particle, nucleus]
        # Insert the original start pose before baking the shifted locator.
        # Do not key a constraint/expression-driven non-output channel: Maya
        # would insert a pairBlend and disable the existing rig driver.
        safe_attributes = []
        for attribute in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']:
            plug = control + '.' + attribute
            if cmds.getAttr(plug, lock=True) or not cmds.getAttr(plug, keyable=True):
                continue
            sources = cmds.listConnections(plug, source=True, destination=False) or []
            if all(cmds.nodeType(n).startswith(('animCurveT', 'animBlendNode')) for n in sources):
                safe_attributes.append(attribute)
        if safe_attributes:
            cmds.setKeyframe(control, time=self.start, attribute=safe_attributes)
        cmds.bakeResults(goal, simulation=False, time=(self.start, self.end),
                         minimizeRotation=False, shape=False)
        cmds.delete(goal, constraints=True)
        for attribute, delay in [('translate', self.delay)] + (
                [('rotate', self.delay * self.scale)] if self.rotation else []):
            cmds.keyframe(goal, relative=True, attribute=attribute, timeChange=delay)
            cmds.keyframe(goal, edit=True, relative=True, attribute=attribute,
                          timeChange=-delay, time=(self.start + delay,))
        return goal, [goal]

    def bake_chain(self, nodes, custom=False):
        locs, spacing = self.chain(nodes)
        cmds.currentTime(self.start)
        if self.add_to_layer and self.layer is None:
            self.layer = cmds.animLayer('OverlapHelper#', override=True)
        for i, node in enumerate(nodes):
            if (custom and i > 0) or (self.ignore_first and i == 0):
                continue
            attributes = [('rotate' if self.rotation else 'translate') + axis
                          for axis in self.axes if not cmds.getAttr(
                              node + '.' + ('rotate' if self.rotation else 'translate') + axis, lock=True)]
            if not attributes:
                continue
            cmds.currentTime(self.start)
            driver, garbage = self.driver(locs[i], spacing, node)
            if self.rotation:
                parent = self.locator('rotation')
                aim = self.locator('aim')
                target = self.locator('target')
                cmds.parent(aim, target, parent, absolute=True)
                cmds.parentConstraint(locs[i], parent)
                cmds.aimConstraint(driver, aim, weight=1, aimVector=(0, 1, 0),
                                   upVector=(0, 1, 0), worldUpType='vector',
                                   worldUpVector=(0, 1, 0), skip='y')
                cmds.parentConstraint(aim, target, maintainOffset=True,
                                      skipTranslate=('x', 'y', 'z'), weight=1)
                driver = target
                garbage.append(parent)
            copy = cmds.duplicate(node, parentOnly=True,
                                  name='overlapHelperTemp_copy#')[0]
            self.temporary.append(copy)
            for attribute in attributes:
                others = tuple(a.lower() for a in 'XYZ' if a != attribute[-1])
                cmds.parentConstraint(driver, copy, maintainOffset=True,
                                      skipTranslate=('x', 'y', 'z') if self.rotation else others,
                                      skipRotate=others if self.rotation else ('x', 'y', 'z'))
            cmds.bakeResults(copy, time=(self.start, self.end), simulation=True,
                             attribute=['rotateX', 'rotateY', 'rotateZ'] if self.rotation
                             else ['translateX', 'translateY', 'translateZ'])
            if self.layer:
                cmds.animLayer(self.layer, edit=True,
                               attribute=[node + '.' + attr for attr in attributes])
                cmds.select(copy, replace=True)
                cmds.setInfinity(preInfinite='constant', postInfinite='constant')
                cmds.copyKey(copy, attribute=attributes)
                cmds.pasteKey(node, option='replace', animLayer=self.layer, attribute=attributes)
            else:
                cmds.copyKey(copy, attribute=attributes, time=(self.start, self.end))
                cmds.pasteKey(node, option='replace', attribute=attributes,
                              time=(self.start, self.end))
            self.delete(garbage + [copy])
        self.delete(locs)
        return self.layer

    @staticmethod
    def delete(nodes):
        existing = list(dict.fromkeys(n for n in nodes if cmds.objExists(n)))
        if existing:
            cmds.delete(existing)

    def cleanup(self):
        self.delete(self.temporary)
