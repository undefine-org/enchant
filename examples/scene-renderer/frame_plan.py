"""One clock contract for dense film plans and bounded sparse review plans."""
import math


def validate_clock(plan, total):
    version = plan.get('version')
    frames = plan.get('frames')
    if type(version) is not int or version not in (1, 2) or not isinstance(frames, list):
        raise ValueError('Unsupported frame plan')
    if version == 1:
        if 'selection' in plan or len(frames) != total:
            raise ValueError('A film plan requires its complete clock')
        indices = list(range(total))
    else:
        indices = plan.get('selection')
        if (not isinstance(indices, list) or not 1 <= len(indices) <= 64
                or len(frames) != len(indices)
                or any(type(k) is not int or not 0 <= k < total for k in indices)
                or indices != sorted(set(indices))):
            raise ValueError('Invalid sparse review selection')
    for k, frame in zip(indices, frames):
        time = frame.get('time') if isinstance(frame, dict) else None
        if (not isinstance(frame, dict) or type(frame.get('frame')) is not int
                or frame['frame'] != k or type(time) not in (int, float)
                or not math.isfinite(time) or abs(time - k / 60) > 1e-8):
            raise ValueError('Invalid frame clock')
    return indices


def select_frames(plan, total, selected, defaults, film):
    indices = validate_clock(plan, total)
    if film and plan['version'] != 1:
        raise ValueError('Sparse review plans cannot be exported as a film')
    requested = ([int(k) for k in selected.split(',')] if selected else
                 (plan['selection'] if plan['version'] == 2 else defaults))
    if (not requested or len(requested) > 64 or len(set(requested)) != len(requested)
            or any(type(k) is not int or k not in indices for k in requested)):
        raise ValueError('Requested frame was not captured')
    return dict(zip(indices, plan['frames'])), requested
