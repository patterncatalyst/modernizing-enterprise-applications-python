"""Shared layout helpers for this book's diagram specs.

Thin helpers on top of scripts/generate_diagram.py: octagon layouts for
8-step loops, and a box-edge connector so arrows terminate on the boundary
of the box they're pointing at (not its center): per the diagram-generator
skill's "every edge must terminate on a box edge" rule.

Not part of the vendored generator; local to this diagram set.
"""
import math


def node(x, y, w, h, lines, style="box"):
    return {"x": x, "y": y, "w": w, "h": h, "lines": lines, "style": style}


def octagon_positions(cx, cy, rx, ry):
    """8 (x, y) centers around an ellipse: N, NE, E, SE, S, SW, W, NW: clockwise from top."""
    angles = [-90, -45, 0, 45, 90, 135, 180, -135]
    return [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a))) for a in angles]


def rect_edge_point(box, target):
    """Point on box's boundary facing target=(tx,ty)."""
    cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
    tx, ty = target
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return (cx, cy)
    scales = []
    if dx != 0:
        scales.append((box["w"] / 2) / abs(dx))
    if dy != 0:
        scales.append((box["h"] / 2) / abs(dy))
    scale = min(scales)
    return (cx + dx * scale, cy + dy * scale)


def connect(a, b, **kw):
    """Edge dict from box a to box b, endpoints on their facing edges."""
    ca = (a["x"] + a["w"] / 2, a["y"] + a["h"] / 2)
    cb = (b["x"] + b["w"] / 2, b["y"] + b["h"] / 2)
    x1, y1 = rect_edge_point(a, cb)
    x2, y2 = rect_edge_point(b, ca)
    e = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
    e.update(kw)
    return e
