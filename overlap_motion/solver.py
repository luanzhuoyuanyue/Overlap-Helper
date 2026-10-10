"""Sampled world-space motion. Positions are triples; quaternions are xyzw."""

import math


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _scale(v, s):
    return tuple(x * s for x in v)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _unit(v):
    size = math.sqrt(_dot(v, v))
    return _scale(v, 1.0 / size) if size > 1e-12 else v


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _lerp(a, b, t):
    return _add(_scale(a, 1.0 - t), _scale(b, t))


def _multiply(a, b):
    xyz = _add(_add(_scale(b[:3], a[3]), _scale(a[:3], b[3])),
               _cross(a[:3], b[:3]))
    return xyz + (a[3] * b[3] - _dot(a[:3], b[:3]),)


def rotate(q, vector):
    """Rotate a vector by a unit xyzw quaternion."""
    t = _scale(_cross(q[:3], vector), 2.0)
    return _add(vector, _add(_scale(t, q[3]), _cross(q[:3], t)))


def _slerp(a, b, t):
    cosine = _dot(a, b)
    if cosine < 0:
        b, cosine = _scale(b, -1.0), -cosine
    if cosine > 0.9995:
        return _unit(_lerp(a, b, t))
    angle = math.acos(max(-1.0, min(1.0, cosine)))
    return _add(_scale(a, math.sin((1.0 - t) * angle) / math.sin(angle)),
                _scale(b, math.sin(t * angle) / math.sin(angle)))


def _between(a, b):
    a, b = _unit(a), _unit(b)
    if _dot(b, b) < 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    cosine = _dot(a, b)
    if cosine < -0.999999:
        seed = (1, 0, 0) if abs(a[0]) < 0.9 else (0, 1, 0)
        return _unit(_cross(a, seed)) + (0.0,)
    return _unit(_cross(a, b) + (1.0 + cosine,))


def _sample(values, frame, cycle, quaternion=False):
    last = len(values) - 1
    frame = frame % last if cycle else max(0.0, min(float(last), frame))
    index = int(math.floor(frame))
    fraction = frame - index
    blend = _slerp if quaternion else _lerp
    return blend(values[index], values[min(index + 1, last)], fraction)


def _spring(values, response, damping, cycle):
    # Implicit Euler with substeps stays stable even for short response periods.
    omega = 2.0 * math.pi / response
    dt = 1.0 / 8.0
    denominator = 1.0 + 2.0 * dt * damping * omega + dt * dt * omega * omega
    position, velocity = values[0], (0.0, 0.0, 0.0)

    def advance(previous, target, position, velocity):
        for substep in range(1, 9):
            goal = _lerp(previous, target, substep / 8.0)
            velocity = _scale(_add(velocity, _scale(_sub(goal, position),
                                                   dt * omega * omega)),
                              1.0 / denominator)
            position = _add(position, _scale(velocity, dt))
        return position, velocity

    if cycle:
        # Ten decay time constants suppress startup transients before recording.
        warm_frames = 10.0 / (min(damping, 1.0) * omega)
        periods = max(2, int(math.ceil(warm_frames / (len(values) - 1))))
        for _ in range(periods):
            for i in range(1, len(values)):
                position, velocity = advance(values[i - 1], values[i], position, velocity)
    result = [position]
    for i in range(1, len(values)):
        position, velocity = advance(values[i - 1], values[i], position, velocity)
        result.append(position)
    if cycle:
        result[-1] = result[0]
    return result


def _soft(values, response, cycle):
    """A first-order lag: smooth following without physical overshoot."""
    alpha = 1.0 - math.exp(-1.0 / response)
    position = values[0]
    if cycle:
        periods = max(2, int(math.ceil(10.0 * response / (len(values) - 1))))
        for _ in range(periods):
            for target in values[1:]:
                position = _lerp(position, target, alpha)
    result = [position]
    for target in values[1:]:
        position = _lerp(position, target, alpha)
        result.append(position)
    if cycle:
        result[-1] = result[0]
    return result


def _rotation_lag(values, response, damping, cycle, mode):
    """Filter orientation too, including rotation about the virtual-tip axis."""
    dt = 1.0 / 8.0
    omega = 2.0 * math.pi / response
    denominator = 1 + 2 * dt * damping * omega + dt * dt * omega * omega
    orientation, velocity = values[0], (0.0, 0.0, 0.0)

    def advance(previous, target, orientation, velocity):
        for substep in range(1, 9):
            goal = _slerp(previous, target, substep / 8.0)
            if mode == 'soft':
                orientation = _slerp(orientation, goal, 1 - math.exp(-dt / response))
                continue
            inverse = _scale(orientation[:3], -1) + (orientation[3],)
            error = _multiply(goal, inverse)
            if error[3] < 0:
                error = _scale(error, -1)
            angle = 2 * math.atan2(math.sqrt(_dot(error[:3], error[:3])), error[3])
            displacement = _scale(_unit(error[:3]), angle)
            velocity = _scale(_add(velocity, _scale(displacement, dt * omega * omega)),
                              1.0 / denominator)
            step = math.sqrt(_dot(velocity, velocity)) * dt
            delta = _scale(_unit(velocity), math.sin(step / 2)) + (math.cos(step / 2),)
            orientation = _unit(_multiply(delta, orientation))
        return orientation, velocity

    if cycle:
        warm_frames = 10 * response if mode == 'soft' else 10 / (min(damping, 1.0) * omega)
        for _ in range(max(2, int(math.ceil(warm_frames / (len(values) - 1))))):
            for i in range(1, len(values)):
                orientation, velocity = advance(values[i - 1], values[i], orientation, velocity)
    result = [orientation]
    for i in range(1, len(values)):
        orientation, velocity = advance(values[i - 1], values[i], orientation, velocity)
        result.append(orientation)
    if cycle:
        result[-1] = result[0]
    return result


def solve(positions, rotations, delay=2.0, mode='spring', response=12.0,
          damping=0.35, strength=1.0, axis=(1, 0, 0), length=5.0, cycle=False,
          filter_twist=False):
    """Return delayed/spring positions and swinging world orientations.

    response is the undamped period in frames; damping is a damping ratio.
    In a cycle the last frame is the first frame of the next repetition.
    """
    if len(positions) < 2 or len(positions) != len(rotations):
        raise ValueError('Need matching position/rotation samples for at least two frames.')
    if mode not in ('delay', 'spring', 'soft'):
        raise ValueError('Unknown overlap mode.')
    if not all(math.isfinite(v) for v in (delay, response, damping, strength, length)):
        raise ValueError('Parameters must be finite.')
    if delay < 0 or not 1 <= response <= 240 or not 0.05 <= damping <= 2:
        raise ValueError('Delay >= 0, response 1..240, damping 0.05..2 required.')
    if not 0 <= strength <= 1 or length <= 0 or _dot(axis, axis) < 1e-12:
        raise ValueError('Strength 0..1 and positive length/nonzero axis required.')
    if strength == 0:
        return list(positions), list(rotations)

    axis = _unit(axis)
    rotations = [_unit(q) for q in rotations]
    positions, rotations = list(positions), list(rotations)
    if cycle:
        positions[-1], rotations[-1] = positions[0], rotations[0]
    delayed_p = [_sample(positions, i - delay, cycle) for i in range(len(positions))]
    delayed_q = [_sample(rotations, i - delay, cycle, True) for i in range(len(positions))]
    if mode == 'delay':
        result_p, result_q = delayed_p, delayed_q
    else:
        tips = [_add(p, _scale(rotate(q, axis), length)) for p, q in zip(delayed_p, delayed_q)]
        if mode == 'soft':
            result_p = _soft(delayed_p, response, cycle)
            result_tips = _soft(tips, response, cycle)
        else:
            result_p = _spring(delayed_p, response, damping, cycle)
            result_tips = _spring(tips, response, damping, cycle)
        basis = (_rotation_lag(delayed_q, response, damping, cycle, mode)
                 if filter_twist else rotations)
        result_q = [_multiply(_between(rotate(q, axis), _sub(tip, pivot)), q)
                    for q, tip, pivot in zip(basis, result_tips, positions)]
    return ([_lerp(original, result, strength) for original, result in zip(positions, result_p)],
            [_slerp(original, result, strength) for original, result in zip(rotations, result_q)])
