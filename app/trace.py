"""Minimal bitmap-to-vector outline tracer (MIT, part of this project).

Turns a binary mask into smooth closed SVG paths:
1. collect the pixel-boundary ("crack") edges around foreground pixels, oriented clockwise;
2. link them into closed loops;
3. simplify each loop with Ramer-Douglas-Peucker;
4. smooth it into cubic Béziers (Catmull-Rom).

Good enough for sticker / die-cut outlines of already smoothed masks. It is not a general
purpose replacement for tools like potrace.
"""

import numpy as np

# Directions in screen coordinates (y grows downwards).
RIGHT, DOWN, LEFT, UP = (1, 0), (0, 1), (-1, 0), (0, -1)


def _edges(mask: np.ndarray) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Outgoing boundary edges per grid vertex, oriented so foreground is on the right."""
    m = np.pad(mask.astype(bool), 1)
    out: dict[tuple[int, int], list[tuple[int, int]]] = {}

    def add(ys, xs, start, d):
        for y, x in zip(ys.tolist(), xs.tolist()):
            out.setdefault((x + start[0], y + start[1]), []).append(d)

    fg = m[1:-1, 1:-1]
    # Coordinates below are in the unpadded pixel grid: pixel (r, c) spans [c, c+1] x [r, r+1].
    ys, xs = np.nonzero(fg & ~m[:-2, 1:-1])   # background above -> top edge, left to right
    add(ys, xs, (0, 0), RIGHT)
    ys, xs = np.nonzero(fg & ~m[1:-1, 2:])    # background right -> right edge, downwards
    add(ys, xs, (1, 0), DOWN)
    ys, xs = np.nonzero(fg & ~m[2:, 1:-1])    # background below -> bottom edge, right to left
    add(ys, xs, (1, 1), LEFT)
    ys, xs = np.nonzero(fg & ~m[1:-1, :-2])   # background left -> left edge, upwards
    add(ys, xs, (0, 1), UP)
    return out


def _loops(out: dict[tuple[int, int], list[tuple[int, int]]]) -> list[list[tuple[int, int]]]:
    loops = []
    while out:
        start = next(iter(out))
        v, d = start, None
        pts = []
        while True:
            options = out.get(v)
            if not options:
                break
            if d is not None and len(options) > 1:
                # At pixels touching diagonally, prefer turning right to keep shapes separate.
                right = (-d[1], d[0])
                nd = right if right in options else options[0]
            else:
                nd = options[0]
            options.remove(nd)
            if not options:
                del out[v]
            if nd != d:
                pts.append(v)  # keep corners only
            d = nd
            v = (v[0] + d[0], v[1] + d[1])
            if v == start:
                break
        if len(pts) >= 3:
            loops.append(pts)
    return loops


def _area(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _rdp(pts: np.ndarray, eps: float) -> np.ndarray:
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    ab = b - a
    norm = np.hypot(*ab)
    if norm == 0:
        dist = np.hypot(*(pts - a).T)
    else:
        dist = np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / norm
    i = int(np.argmax(dist))
    if dist[i] > eps:
        left = _rdp(pts[: i + 1], eps)
        right = _rdp(pts[i:], eps)
        return np.vstack([left[:-1], right])
    return np.vstack([a, b])


def _simplify_closed(pts: np.ndarray, eps: float) -> np.ndarray:
    # Split the loop at the point farthest from the first one, simplify both halves.
    far = int(np.argmax(np.hypot(*(pts - pts[0]).T)))
    closed = np.vstack([pts, pts[:1]])
    first = _rdp(closed[: far + 1], eps)
    second = _rdp(closed[far:], eps)
    return np.vstack([first[:-1], second[:-1]])


def _densify(poly: np.ndarray, max_step: float) -> np.ndarray:
    """Add points along long straight runs so the smoothing spline can't overshoot at corners."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        steps = max(1, int(np.ceil(np.hypot(*(b - a)) / max_step)))
        for t in range(steps):
            out.append(a + (b - a) * (t / steps))
    return np.asarray(out)


def trace(mask: np.ndarray, min_area: float = 8.0, tolerance: float = 0.9, max_step: float = 4.0) -> list[np.ndarray]:
    """Return closed polygons (float arrays of shape (n, 2), x/y in pixel units)."""
    polys = []
    for loop in _loops(_edges(mask)):
        pts = np.asarray(loop, dtype=float)
        if _area(pts) < min_area:
            continue
        simple = _simplify_closed(pts, tolerance)
        if len(simple) >= 3:
            polys.append(_densify(simple, max_step))
    return polys


def smooth_path(poly: np.ndarray, fmt) -> str:
    """Closed Catmull-Rom spline through the polygon points, as SVG cubic Béziers."""
    n = len(poly)
    p = poly
    d = [f"M{fmt(p[0])}"]
    for i in range(n):
        p0, p1, p2, p3 = p[i - 1], p[i], p[(i + 1) % n], p[(i + 2) % n]
        c1 = p1 + (p2 - p0) / 6.0
        c2 = p2 - (p3 - p1) / 6.0
        d.append(f"C{fmt(c1)} {fmt(c2)} {fmt(p2)}")
    d.append("Z")
    return "".join(d)
