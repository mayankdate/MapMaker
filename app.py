"""Personal Map Studio: local browser app for making printable street maps.

Run: python app.py
Then open http://127.0.0.1:5000 in your browser (opens automatically).
"""
from __future__ import annotations

import io
import json
import threading
import webbrowser
from pathlib import Path

import matplotlib.pyplot as plt
import osmnx as ox
import requests
from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from mapstudio import defaults, fetch, render

PROJECT_ROOT = Path(__file__).resolve().parent
MARKERS_DIR = PROJECT_ROOT / "markers"
DEFAULTS_DIR = PROJECT_ROOT / "assets" / "default_markers"
OUTPUTS_DIR = PROJECT_ROOT / "Outputs"
CACHE_DIR = PROJECT_ROOT / ".osm_cache"

for directory in (MARKERS_DIR, OUTPUTS_DIR, CACHE_DIR):
    directory.mkdir(exist_ok=True)
defaults.ensure_defaults(DEFAULTS_DIR)

ox.settings.use_cache = True
ox.settings.cache_folder = str(CACHE_DIR)
ox.settings.requests_timeout = 180
ox.settings.user_agent = "PersonalMapStudio/1.0 (local personal cartographic artwork)"

app = Flask(__name__, static_folder="static", template_folder="templates")

STATE = {"bbox": None, "layers": None, "include_buildings": None}

COMBINED_EXTENSIONS = {"combined_png": "png", "combined_pdf": "pdf", "combined_svg": "svg"}
KNOWN_FORMATS = {*COMBINED_EXTENSIONS, "layer_pngs", "layer_geojson"}


@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@app.route("/api/icons")
def list_icons():
    default_names = sorted(p.name for p in DEFAULTS_DIR.glob("*.png"))
    user_names = sorted(p.name for p in MARKERS_DIR.glob("*.png"))
    return jsonify({
        "defaults": [{"name": n, "url": f"/icons/default/{n}"} for n in default_names],
        "user": [{"name": n, "url": f"/icons/user/{n}"} for n in user_names],
    })


@app.route("/icons/default/<path:name>")
def icon_default(name):
    return send_from_directory(DEFAULTS_DIR, name)


@app.route("/icons/user/<path:name>")
def icon_user(name):
    return send_from_directory(MARKERS_DIR, name)


@app.route("/api/geocode")
def geocode():
    query = request.args.get("q", "").strip()
    if not query:
        abort(400, "Missing query parameter q")
    response = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "json", "limit": 8, "addressdetails": 1},
        headers={"User-Agent": ox.settings.user_agent},
        timeout=15,
    )
    response.raise_for_status()
    results = [
        {
            "label": item["display_name"],
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "type": item.get("type"),
            "bbox": [float(b) for b in item["boundingbox"]] if "boundingbox" in item else None,
        }
        for item in response.json()
    ]
    return jsonify({"results": results})


@app.route("/api/fetch", methods=["POST"])
def fetch_layers():
    body = request.get_json(force=True)
    bbox = tuple(body["bbox"])
    include_buildings = bool(body.get("include_buildings", False))
    height, width = fetch.area_km(bbox)
    if min(height, width) <= 0 or max(height, width) > 35:
        abort(400, f"Select an area at most 35 km per side (currently {width:.1f} x {height:.1f} km).")
    if max(abs(bbox[0]), abs(bbox[2])) > 80:
        abort(400, "Choose an area between 80 S and 80 N for this print projection.")
    layers = fetch.collect_layers(bbox, include_buildings)
    STATE["bbox"] = bbox
    STATE["layers"] = layers
    STATE["include_buildings"] = include_buildings
    return jsonify({
        "bbox": list(bbox),
        "size_km": {"width": round(width, 2), "height": round(height, 2)},
        "counts": fetch.layer_counts(layers),
    })


def _payload(body):
    """Extract common render inputs from a preview/export request body."""
    style = body["style"]
    markers = body.get("markers", [])
    for point in markers:
        point["lat"] = float(point["lat"])
        point["lon"] = float(point["lon"])
    title = body.get("title", "")
    title_placement = body.get("title_placement", "bottom")
    long_side_in = float(body.get("long_side_in", 12))
    marker_size = float(body.get("marker_size", 15))
    page_inches = render.page_inches_from_bbox(STATE["bbox"], long_side_in)
    return {
        "style": style,
        "markers": markers,
        "title": title,
        "title_placement": title_placement,
        "page_inches": page_inches,
        "marker_size": marker_size,
    }


@app.route("/api/preview", methods=["POST"])
def preview():
    if STATE["layers"] is None:
        abort(400, "Fetch features before requesting a preview.")
    body = request.get_json(force=True)
    params = _payload(body)
    fig = render.draw(
        bbox=STATE["bbox"], layers=STATE["layers"],
        marker_dirs=[MARKERS_DIR, DEFAULTS_DIR],
        **params,
    )
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=120,
                facecolor=fig.get_facecolor(), pad_inches=0)
    plt.close(fig)
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


@app.route("/api/export", methods=["POST"])
def export():
    if STATE["layers"] is None:
        abort(400, "Fetch features before exporting.")
    body = request.get_json(force=True)
    formats = body.get("formats", [])
    if not formats:
        abort(400, "Select at least one export format.")
    unknown = [f for f in formats if f not in KNOWN_FORMATS]
    if unknown:
        abort(400, f"Unknown export format(s): {unknown}")
    params = _payload(body)

    title = params["title"]
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in title).strip("_") or "city_map"
    export_dir = OUTPUTS_DIR / slug
    export_dir.mkdir(parents=True, exist_ok=True)
    written = []

    combined_needed = [f for f in formats if f in COMBINED_EXTENSIONS]
    if combined_needed:
        fig = render.draw(
            bbox=STATE["bbox"], layers=STATE["layers"],
            marker_dirs=[MARKERS_DIR, DEFAULTS_DIR],
            **params,
        )
        for fmt in combined_needed:
            ext = COMBINED_EXTENSIONS[fmt]
            target = export_dir / f"{slug}.{ext}"
            fig.savefig(target, format=ext, dpi=300,
                        facecolor=fig.get_facecolor(), pad_inches=0)
            written.append(f"{slug}.{ext}")
        plt.close(fig)

    if "layer_pngs" in formats:
        layer_dir = export_dir / "layer_pngs"
        layer_dir.mkdir(exist_ok=True)
        style = params["style"]
        for name in render.ALL_LAYER_NAMES:
            if name in render.MAP_LAYER_ORDER:
                if not style.get(f"show_{name}", True):
                    continue
                if STATE["layers"][name].empty:
                    continue
            if name == "markers" and not params["markers"]:
                continue
            if name == "place_labels":
                if not style.get("show_place_labels", False):
                    continue
                if STATE["layers"]["place_labels"].empty:
                    continue
            if name == "road_labels":
                if not style.get("show_road_labels", False):
                    continue
                if STATE["layers"]["road_labels"].empty:
                    continue
            fig = render.draw_layer(
                name=name, bbox=STATE["bbox"], layers=STATE["layers"],
                marker_dirs=[MARKERS_DIR, DEFAULTS_DIR],
                **params,
            )
            target = layer_dir / f"{name}.png"
            if name == "background":
                fig.savefig(target, format="png", dpi=300,
                            facecolor=fig.get_facecolor(), pad_inches=0)
            else:
                fig.savefig(target, format="png", dpi=300,
                            transparent=True, pad_inches=0)
            plt.close(fig)
            written.append(f"layer_pngs/{name}.png")

    if "layer_geojson" in formats:
        geojson_dir = export_dir / "layer_geojson"
        geojson_dir.mkdir(exist_ok=True)
        for name, frame in STATE["layers"].items():
            if not frame.empty:
                target = geojson_dir / f"{name}.geojson"
                target.write_text(frame.to_crs(4326).to_json(), encoding="utf-8")
                written.append(f"layer_geojson/{name}.geojson")

    marker_features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
            "properties": {"label": p.get("label", ""), "icon": p.get("icon")},
        }
        for p in params["markers"]
    ]
    (export_dir / "markers.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": marker_features}, indent=2),
        encoding="utf-8",
    )
    written.append("markers.geojson")

    (export_dir / "settings.json").write_text(
        json.dumps({
            "bbox_south_west_north_east": list(STATE["bbox"]),
            "title": title,
            "title_placement": params["title_placement"],
            "long_side_in": float(body.get("long_side_in", 12)),
            "page_inches": list(params["page_inches"]),
            "marker_size": params["marker_size"],
            "style": params["style"],
            "include_buildings": STATE["include_buildings"],
            "markers": params["markers"],
            "formats": formats,
        }, indent=2),
        encoding="utf-8",
    )
    written.append("settings.json")

    return jsonify({
        "export_dir": str(export_dir.relative_to(PROJECT_ROOT)),
        "page_inches": [round(v, 2) for v in params["page_inches"]],
        "files": written,
    })


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


def _open_browser():
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    threading.Timer(1.0, _open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
