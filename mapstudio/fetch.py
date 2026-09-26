"""Fetch OSM features for a bounding box and sort them into map layers."""
from __future__ import annotations

import math

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import Point, box
from shapely.ops import polygonize, unary_union

POLYGONS = {"Polygon", "MultiPolygon"}
LINES = {"LineString", "MultiLineString"}

MAJOR_HIGHWAYS = {
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link",
}
PATH_HIGHWAYS = {"footway", "path", "steps", "cycleway", "bridleway", "pedestrian"}
PLACE_TIERS = {"city", "town", "borough", "district",
               "suburb", "neighbourhood", "quarter",
               "village", "hamlet"}


def area_km(bbox):
    """Return (height_km, width_km) for a (south, west, north, east) bbox."""
    south, west, north, east = bbox
    height = (north - south) * 111.2
    width = (east - west) * 111.2 * math.cos(math.radians((south + north) / 2))
    return height, width


def _tag_matches(value, targets=None):
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return any(_tag_matches(item, targets) for item in value)
    if not isinstance(value, str):
        return False
    return bool(value) if targets is None else value in targets


def _tagged(frame, column, targets=None):
    if column not in frame:
        return frame.iloc[0:0].copy()
    return frame.loc[frame[column].map(lambda v: _tag_matches(v, targets))].copy()


def _geom(frame, types):
    return frame.loc[frame.geometry.geom_type.isin(types)].copy()


def _coastal_water(frame, bbox):
    """Turn OSM coastline ways into sea polygons. OSM draws land on the left."""
    coast = _geom(_tagged(frame, "natural", {"coastline"}), LINES)
    empty = gpd.GeoDataFrame(geometry=[], crs=3857)
    if coast.empty:
        return empty
    south, west, north, east = bbox
    boundary = gpd.GeoSeries([box(west, south, east, north)], crs=4326).to_crs(3857).iloc[0]
    segments = []
    for line in coast.to_crs(3857).geometry:
        clipped = line.intersection(boundary)
        if clipped.geom_type == "LineString":
            segments.append(clipped)
        elif clipped.geom_type == "MultiLineString":
            segments.extend(clipped.geoms)
    if not segments:
        return empty
    polygons = list(polygonize(unary_union([boundary.boundary, *segments])))
    sea = []
    for polygon in polygons:
        for line in segments:
            if not polygon.boundary.intersects(line) or line.length < 2:
                continue
            start = line.interpolate(line.length * 0.49)
            end = line.interpolate(line.length * 0.51)
            dx, dy = end.x - start.x, end.y - start.y
            length = math.hypot(dx, dy)
            mid = line.interpolate(line.length * 0.5)
            right = Point(mid.x + dy / length, mid.y - dx / length)
            if polygon.contains(right):
                sea.append(polygon)
                break
    if not sea:
        return empty
    return gpd.GeoDataFrame(geometry=sea, crs=3857)


def collect_layers(bbox, include_buildings):
    """Fetch OSM features for the bbox and return a dict of GeoDataFrames in EPSG:3857.

    bbox is (south, west, north, east). Result keys: water, parks, buildings, rail,
    minor, major, paths.
    """
    south, west, north, east = bbox
    tags = {
        "highway": True,
        "natural": ["water", "wood", "grassland", "coastline"],
        "waterway": True,
        "landuse": ["reservoir", "basin", "forest", "grass", "meadow"],
        "leisure": ["park", "garden", "nature_reserve", "recreation_ground"],
        "railway": True,
        "place": True,
    }
    if include_buildings:
        tags["building"] = True

    frame = ox.features_from_bbox((west, south, east, north), tags=tags)
    frame = frame.loc[frame.intersects(box(west, south, east, north))].copy()

    roads = _geom(_tagged(frame, "highway"), LINES)
    major = roads.loc[roads.highway.map(lambda v: _tag_matches(v, MAJOR_HIGHWAYS))].copy()
    paths = roads.loc[roads.highway.map(lambda v: _tag_matches(v, PATH_HIGHWAYS))].copy()
    minor = roads.drop(index=major.index.union(paths.index), errors="ignore")

    water = pd.concat([
        _geom(_tagged(frame, "natural", {"water"}), POLYGONS),
        _geom(_tagged(frame, "landuse", {"reservoir", "basin"}), POLYGONS),
        _geom(_tagged(frame, "waterway"), POLYGONS),
    ])
    parks = pd.concat([
        _geom(_tagged(frame, "leisure"), POLYGONS),
        _geom(_tagged(frame, "landuse", {"forest", "grass", "meadow"}), POLYGONS),
        _geom(_tagged(frame, "natural", {"wood", "grassland"}), POLYGONS),
    ])

    result = {
        "water": water.loc[~water.index.duplicated(keep="first")],
        "parks": parks.loc[~parks.index.duplicated(keep="first")],
        "buildings": _geom(_tagged(frame, "building"), POLYGONS),
        "rail": _geom(_tagged(frame, "railway"), LINES),
        "minor": minor,
        "major": major,
        "paths": paths,
    }
    projected = {}
    for key, value in result.items():
        if len(value):
            projected[key] = value.to_crs(3857)
        else:
            projected[key] = value.set_crs(4326, allow_override=True).to_crs(3857)

    sea = _coastal_water(frame, bbox)
    if not sea.empty:
        projected["water"] = gpd.GeoDataFrame(
            pd.concat([projected["water"], sea], ignore_index=True), crs=3857
        )

    projected["place_labels"] = _build_place_labels(frame)
    projected["road_labels"] = _build_road_labels(projected["major"], projected["minor"])
    return projected


def _build_place_labels(frame):
    """Extract named place features into a Point GeoDataFrame with a 'place' tier column."""
    empty = gpd.GeoDataFrame(
        {"name": [], "place": []}, geometry=gpd.GeoSeries([], crs=3857)
    )
    if "place" not in frame.columns or "name" not in frame.columns:
        return empty
    places = _tagged(frame, "place", PLACE_TIERS)
    places = places.loc[places["name"].notna()].copy()
    if places.empty:
        return empty
    places["geometry"] = places.geometry.apply(
        lambda g: g if g.geom_type == "Point" else g.representative_point()
    )
    trimmed = gpd.GeoDataFrame(
        places[["name", "place"]].reset_index(drop=True),
        geometry=places.geometry.reset_index(drop=True),
        crs=places.crs,
    )
    trimmed = trimmed.drop_duplicates(subset=["name"])
    return trimmed.to_crs(3857)


def _build_road_labels(major, minor):
    """Merge road segments by name into one representative point per road, per tier."""
    empty = gpd.GeoDataFrame(
        {"name": [], "tier": []}, geometry=gpd.GeoSeries([], crs=3857)
    )
    parts = []
    for gdf, tier in ((major, "major"), (minor, "minor")):
        if gdf.empty or "name" not in gdf.columns:
            continue
        named = gdf.loc[gdf["name"].notna()]
        if named.empty:
            continue
        rows = []
        for name, group in named.groupby("name"):
            merged = unary_union(list(group.geometry))
            rows.append({"name": name, "tier": tier,
                         "geometry": merged.representative_point()})
        parts.append(gpd.GeoDataFrame(rows, crs=3857))
    if not parts:
        return empty
    return gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True), crs=3857
    )


def layer_counts(layers):
    return {name: int(len(frame)) for name, frame in layers.items()}
