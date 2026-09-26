"""Generate the bundled default marker PNGs on first launch."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
COLOR = (225, 173, 105, 255)  # matches the reference maps' gold


def _blank():
    return Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))


def _cross(image):
    draw = ImageDraw.Draw(image)
    thickness = SIZE // 6
    length = int(SIZE * 0.66)
    x0 = (SIZE - length) // 2
    x1 = x0 + length
    y_mid = SIZE // 2
    draw.rectangle([x0, y_mid - thickness // 2, x1, y_mid + thickness // 2], fill=COLOR)
    x_mid = SIZE // 2
    draw.rectangle([x_mid - thickness // 2, x0, x_mid + thickness // 2, x1], fill=COLOR)


def _dot(image):
    draw = ImageDraw.Draw(image)
    r = int(SIZE * 0.33)
    c = SIZE // 2
    draw.ellipse([c - r, c - r, c + r, c + r], fill=COLOR)


def _ring(image):
    draw = ImageDraw.Draw(image)
    r_out = int(SIZE * 0.36)
    r_in = int(SIZE * 0.24)
    c = SIZE // 2
    draw.ellipse([c - r_out, c - r_out, c + r_out, c + r_out], fill=COLOR)
    draw.ellipse([c - r_in, c - r_in, c + r_in, c + r_in], fill=(0, 0, 0, 0))


def _star(image):
    draw = ImageDraw.Draw(image)
    c = SIZE // 2
    r_out = int(SIZE * 0.42)
    r_in = int(SIZE * 0.18)
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = r_out if i % 2 == 0 else r_in
        points.append((c + radius * math.cos(angle), c + radius * math.sin(angle)))
    draw.polygon(points, fill=COLOR)


def _pin(image):
    draw = ImageDraw.Draw(image)
    c = SIZE // 2
    head_r = int(SIZE * 0.28)
    head_c_y = int(SIZE * 0.36)
    tip_y = int(SIZE * 0.9)
    # Teardrop: circle head with a triangle tail meeting at the tip.
    draw.ellipse(
        [c - head_r, head_c_y - head_r, c + head_r, head_c_y + head_r],
        fill=COLOR,
    )
    tail_half = int(head_r * 0.75)
    draw.polygon(
        [(c - tail_half, head_c_y), (c + tail_half, head_c_y), (c, tip_y)],
        fill=COLOR,
    )
    # Inner hole in the head.
    hole_r = int(head_r * 0.38)
    draw.ellipse(
        [c - hole_r, head_c_y - hole_r, c + hole_r, head_c_y + hole_r],
        fill=(0, 0, 0, 0),
    )


def _heart(image):
    draw = ImageDraw.Draw(image)
    c = SIZE // 2
    lobe_r = int(SIZE * 0.22)
    lobe_y = int(SIZE * 0.38)
    left_x = c - lobe_r
    right_x = c + lobe_r
    draw.ellipse([left_x - lobe_r, lobe_y - lobe_r, left_x + lobe_r, lobe_y + lobe_r], fill=COLOR)
    draw.ellipse([right_x - lobe_r, lobe_y - lobe_r, right_x + lobe_r, lobe_y + lobe_r], fill=COLOR)
    tip_y = int(SIZE * 0.85)
    draw.polygon(
        [
            (left_x - lobe_r, lobe_y),
            (right_x + lobe_r, lobe_y),
            (c, tip_y),
        ],
        fill=COLOR,
    )


SHAPES = {
    "cross.png": _cross,
    "dot.png": _dot,
    "ring.png": _ring,
    "star.png": _star,
    "pin.png": _pin,
    "heart.png": _heart,
}


def ensure_defaults(directory: Path) -> list[str]:
    """Write default markers if missing. Return the filenames."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, painter in SHAPES.items():
        target = directory / name
        if target.is_file():
            continue
        image = _blank()
        painter(image)
        image.save(target, "PNG")
    return list(SHAPES.keys())
