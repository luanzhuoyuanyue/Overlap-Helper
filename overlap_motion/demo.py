"""Create an additive-to-scene sample: moving root and five X-axis controls."""

from maya import cmds


def create():
    cmds.undoInfo(openChunk=True, chunkName='Overlap Motion Demo')
    try:
        root = cmds.group(empty=True, name='OverlapMotion_Demo#')
        controls = []
        parent = root
        for index in range(5):
            node = cmds.circle(name='OM_tail_%02d#' % (index + 1), normal=(1, 0, 0),
                               radius=1.2 - index * 0.16, constructionHistory=False)[0]
            node = cmds.parent(node, parent, relative=True)[0]
            cmds.setAttr(node + '.translateX', 0 if index == 0 else 4)
            cmds.setAttr(node + '.overrideEnabled', 1)
            cmds.setAttr(node + '.overrideColor', 17 if index == 0 else 18)
            # Each link is visual only; it inherits the controller's transform.
            link = cmds.curve(name='OM_link#', degree=1, point=[(0, 0, 0), (4, 0, 0)])
            cmds.parent(cmds.listRelatives(link, shapes=True)[0], node, shape=True, relative=True)
            cmds.delete(link)
            controls.append(cmds.ls(node, long=True)[0])
            parent = node
        for attribute, values in {
            'translateY': [(1, 0), (17, 4), (33, -4), (49, 3), (65, -2), (81, 0), (97, 0)],
            'rotateZ': [(1, 0), (17, 25), (33, -30), (49, 20), (65, -15), (81, 0), (97, 0)]
        }.items():
            for time, value in values:
                cmds.setKeyframe(root, attribute=attribute, time=time, value=value,
                                 inTangentType='auto', outTangentType='auto')
        cmds.select(controls, replace=True)
        return controls
    finally:
        cmds.undoInfo(closeChunk=True)
