"""Render map layers into styled poster or per-layer transparent PNGs.

All renders share the same extent and page dimensions so per-layer PNGs stack
pixel-perfectly on the combined PNG. Page dimensions are derived from the bbox
aspect ratio (in EPSG:3857) so the drawn rectangle is honored — no expansion.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patheffects
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from PIL import Image
from shapely.geometry import box

MAP_LAYER_ORDER = ["water", "parks", "buildings", "rail", "paths", "minor", "major"]
ALL_LAYER_NAMES = ["background", *MAP_LAYER_ORDER, "markers",
                   "road_labels", "place_labels", "labels"]

FILL_LAYERS = {"water", "parks", "buildings"}
Z_ORDER = {"water": 1, "parks": 2, "buildings": 3, "rail": 4, "paths": 5, "minor": 6, "major": 7}
DEFAULT_LINEWIDTHS = {"rail": 0.46, "minor": 0.42, "major": 1.02, "paths": 0.23}
LINE_COLOR_KEYS = {"rail": "rail", "minor": "minor", "major": "major", "paths": "minor"}

PLACE_STYLE = {
    "city":          {"size": 20, "weight": "bold",     "upper": True},
    "town":          {"size": 15, "weight": "bold",     "upper": True},
    "borough":       {"size": 15, "weight": "bold",     "upper": True},
    "district":      {"size": 15, "weight": "bold",     "upper": True},
    "suburb":        {"size": 11, "weight": "semibold", "upper": False},
    "neighbourhood": {"size": 11, "weight": "semibold", "upper": False},
    "quarter":       {"size": 11, "weight": "semibold", "upper": False},
    "village":       {"size":  9, "weight": "normal",   "upper": False},
    "hamlet":        {"size":  9, "weight": "normal",   "upper": False},
}
PLACE_GROUPS = {
    "cities":   {"city"},
    "towns":    {"town", "borough", "district"},
    "suburbs":  {"suburb", "neighbourhood", "quarter"},
    "villages": {"village", "hamlet"},
}


def page_inches_from_bbox(bbox, long_side_in):
    """Return (width_in, height_in) matching the bbox's EPSG:3857 aspect."""
    xmin, ymin, xmax, ymax = _bounds_3857(bbox)
    span_x = xmax - xmin
    span_y = ymax - ymin
    if span_x >= span_y:
        return (float(long_side_in), float(long_side_in) * span_y / span_x)
    return (float(long_side_in) * span_x / span_y, float(long_side_in))


def _bounds_3857(bbox):
    south, west, north, east = bbox
    return gpd.GeoSeries(
        [box(west, south, east, north)], crs=4326
    ).to_crs(3857).total_bounds


def _new_axes(page_inches, bbox, land_color):
    fig, ax = plt.subplots(figsize=page_inches)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    if land_color is None:
        fig.patch.set_alpha(0.0)
        ax.set_facecolor("none")
    else:
        fig.patch.set_facecolor(land_color)
        ax.set_facecolor(land_color)
    xmin, ymin, xmax, ymax = _bounds_3857(bbox)
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")
    ax.autoscale(False)
    return fig, ax


def _draw_map_layer(ax, name, layers, style):
    data = layers[name]
    if data.empty:
        return
    before = len(ax.collections)
    if name in FILL_LAYERS:
        data.plot(ax=ax, color=style[name], linewidth=0, zorder=Z_ORDER[name])
    else:
        data.plot(
            ax=ax,
            color=style[LINE_COLOR_KEYS[name]],
            linewidth=style.get(f"width_{name}", DEFAULT_LINEWIDTHS[name]),
            alpha=0.9 if name == "major" else 0.8,
            zorder=Z_ORDER[name],
        )
    for collection in ax.collections[before:]:
        collection.set_gid(name)


def _draw_markers(ax, markers, style, marker_size, marker_dirs):
    for index, point in enumerate(markers, 1):
        projected = gpd.GeoSeries(
            gpd.points_from_xy([point["lon"]], [point["lat"]]), crs=4326
        ).to_crs(3857).iloc[0]
        icon_name = point.get("icon")
        if icon_name:
            icon_path = _resolve_icon(icon_name, marker_dirs)
            with Image.open(icon_path) as source:
                raster = source.convert("RGBA")
                raster.thumbnail((96, 96))
            zoom = marker_size / max(raster.size)
            artist = AnnotationBbox(
                OffsetImage(raster, zoom=zoom),
                (projected.x, projected.y),
                frameon=False,
                zorder=20,
            )
            ax.add_artist(artist)
        else:
            artist = ax.scatter(
                [projected.x], [projected.y],
                marker="+", s=marker_size ** 2,
                linewidths=max(1.1, marker_size / 7),
                c=style["marker"], zorder=20,
            )
        artist.set_gid(f"marker_{index}")
        if point.get("label"):
            text = ax.annotate(
                point["label"], (projected.x, projected.y),
                xytext=(9, 5), textcoords="offset points",
                color=style["marker"], fontsize=9, weight="bold", zorder=21,
            )
            text.set_path_effects([patheffects.withStroke(linewidth=2.2, foreground=style["land"])])
            text.set_gid(f"marker_label_{index}")


def _draw_place_labels(ax, place_labels, style):
    if place_labels is None or place_labels.empty:
        return
    color = style.get("label", style["text"])
    halo = style["land"]
    show_tiers = set()
    for group_name, tiers in PLACE_GROUPS.items():
        if style.get(f"show_places_{group_name}", False):
            show_tiers.update(tiers)
    for _, row in place_labels.iterrows():
        tier = row["place"]
        if tier not in show_tiers or tier not in PLACE_STYLE:
            continue
        cfg = PLACE_STYLE[tier]
        text_value = row["name"].upper() if cfg["upper"] else row["name"]
        text = ax.text(
            row.geometry.x, row.geometry.y, text_value,
            fontsize=cfg["size"], fontweight=cfg["weight"],
            color=color, ha="center", va="center",
            fontfamily="DejaVu Sans", zorder=25,
        )
        text.set_path_effects([patheffects.withStroke(linewidth=2.5, foreground=halo)])
        text.set_gid(f"place_label_{tier}")


def _draw_road_labels(ax, road_labels, style):
    if road_labels is None or road_labels.empty:
        return
    color = style.get("label", style["text"])
    halo = style["land"]
    show_major = style.get("show_road_labels_major", True)
    show_minor = style.get("show_road_labels_minor", False)
    for _, row in road_labels.iterrows():
        tier = row["tier"]
        if tier == "major" and not show_major:
            continue
        if tier == "minor" and not show_minor:
            continue
        size = 8 if tier == "major" else 7
        text = ax.text(
            row.geometry.x, row.geometry.y, row["name"],
            fontsize=size, fontstyle="italic",
            color=color, ha="center", va="center",
            fontfamily="DejaVu Sans", zorder=24,
        )
        text.set_path_effects([patheffects.withStroke(linewidth=1.5, foreground=halo)])
        text.set_gid(f"road_label_{tier}")


def _draw_labels(ax, title, title_placement, page_inches, style):
    width_in, _ = page_inches
    if title.strip() and title_placement != "hidden":
        if title_placement == "bottom":
            x, y, rotation, ha, va = 0.5, 0.045, 0, "center", "bottom"
        else:
            x, y, rotation, ha, va = 0.095, 0.11, 90, "left", "bottom"
        text = ax.text(
            x, y, title.upper(), transform=ax.transAxes, rotation=rotation,
            ha=ha, va=va, color=style["text"],
            fontsize=min(29, width_in * 2.9),
            fontweight="bold", fontfamily="DejaVu Sans", zorder=30,
        )
        text.set_gid("title")
    if style.get("show_attribution", True):
        credit = ax.text(
            0.985, 0.011, "© OpenStreetMap contributors", transform=ax.transAxes,
            ha="right", va="bottom", color=style["text"], alpha=0.8,
            fontsize=7, zorder=30,
        )
        credit.set_gid("attribution")


def draw(bbox, layers, style, markers, title, title_placement, page_inches,
         marker_size, marker_dirs):
    """Full poster on land-colored background."""
    fig, ax = _new_axes(page_inches, bbox, style["land"])
    ax.set_gid("land")
    for name in MAP_LAYER_ORDER:
        if style.get(f"show_{name}", True):
            _draw_map_layer(ax, name, layers, style)
    _draw_markers(ax, markers, style, marker_size, marker_dirs)
    if style.get("show_road_labels", False):
        _draw_road_labels(ax, layers.get("road_labels"), style)
    if style.get("show_place_labels", False):
        _draw_place_labels(ax, layers.get("place_labels"), style)
    _draw_labels(ax, title, title_placement, page_inches, style)
    return fig


def draw_layer(name, bbox, layers, style, page_inches, markers, title,
               title_placement, marker_size, marker_dirs):
    """Render one named layer only. 'background' is solid land; everything else
    is drawn on a transparent axes so PNGs stack correctly on top of background."""
    if name == "background":
        fig, _ = _new_axes(page_inches, bbox, style["land"])
        return fig
    fig, ax = _new_axes(page_inches, bbox, None)
    if name == "markers":
        _draw_markers(ax, markers, style, marker_size, marker_dirs)
    elif name == "labels":
        _draw_labels(ax, title, title_placement, page_inches, style)
    elif name == "place_labels":
        _draw_place_labels(ax, layers.get("place_labels"), style)
    elif name == "road_labels":
        _draw_road_labels(ax, layers.get("road_labels"), style)
    elif name in MAP_LAYER_ORDER:
        _draw_map_layer(ax, name, layers, style)
    else:
        raise ValueError(f"Unknown layer name: {name}")
    return fig


def _resolve_icon(icon_name, marker_dirs):
    name = Path(icon_name).name
    for directory in marker_dirs:
        candidate = Path(directory) / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Marker icon not found in {marker_dirs}: {name}")
