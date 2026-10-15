# Project instructions for Claude and other coding assistants

Personal Map Studio is a single Python script that runs a local Flask server
and serves a browser UI. Users start it with `python app.py`. It is **not** a
deployed web app, not an Electron wrapper, and no longer a Jupyter notebook —
that earlier notebook version was replaced because its UI was too cramped.

Keep this simple. No fallbacks that silently substitute, no bare
`try/except: pass`, no warning suppression. If something can go wrong, fail
loudly and let the user see it. If a network call fails or an OSM tag is
missing, raise or return a clear error.

## Directory contract

- `app.py` — Flask routes and startup. Owns in-memory `STATE`.
- `mapstudio/fetch.py` — OSMnx fetch, tag classification, coastline
  polygonization. Pure functions; no Flask imports.
- `mapstudio/render.py` — matplotlib poster rendering. Pure functions.
- `mapstudio/defaults.py` — PIL-drawn default markers. Only runs on startup
  and only writes to `assets/default_markers/` (never `markers/`).
- `templates/index.html`, `static/app.js`, `static/style.css` — the UI.
  Vanilla JS + Leaflet, no build step.
- `markers/` — user PNGs. Read-only from the app's perspective; never
  overwrite or delete files here.
- `assets/default_markers/` — bundled defaults. Regenerated on startup if
  missing; safe to delete.
- `Outputs/<slug>/` — exports. The only writable output location.
- `.osm_cache/` — OSMnx cache.

## API contract (frontend ⇄ backend)

- `GET /api/icons` → `{defaults: [{name, url}], user: [{name, url}]}`.
- `GET /api/geocode?q=…` → Nominatim search, up to 8 results.
- `POST /api/fetch` — body `{bbox: [S, W, N, E], include_buildings: bool}`.
  Populates the in-memory `STATE`. Rejects areas over 35 km per side or
  outside 80°S–80°N.
- `POST /api/preview` — body: `{style, markers, title, title_placement,
  long_side_in, marker_size}`. Backend derives `page_inches` from the current
  bbox aspect so the drawn rectangle is honored exactly. Returns a 120 dpi
  PNG. Requires prior fetch.
- `POST /api/export` — same body as preview plus `formats: [...]`. Valid
  format ids: `combined_png`, `combined_pdf`, `combined_svg`, `layer_pngs`,
  `layer_geojson`. Empty or unknown formats → 400.
  `markers.geojson` and `settings.json` are always written.

`STATE` is a single dict at module level — this is a single-user local tool.
If the last fetch is stale (bbox differs), the user re-runs fetch; do not add
implicit re-fetching in preview/export.

## Page aspect ratio

`render.page_inches_from_bbox(bbox, long_side_in)` derives page dimensions
from the bbox's EPSG:3857 aspect ratio. The extent used at render time is the
bbox exactly — no expansion, no cropping. Do not reintroduce the previous
"expand to fit page ratio" logic; users draw the rectangle they want.

## Per-layer PNGs

`render.draw_layer(name, ...)` renders exactly one named layer. `background`
is solid land color; everything else uses a transparent axes. All per-layer
PNGs share the same figure dimensions and extent as the combined render, so
stacking them (in Procreate, Photoshop, or PIL's `alpha_composite`) reproduces
the combined PNG pixel-for-pixel. Do not add per-layer offsets, padding, or
crop.

## Text labels

Two toggleable text overlays sit on top of the map:

- `place_labels`: named `place=*` features (city, town, suburb, neighbourhood,
  quarter, village, hamlet, borough, district). Fetched into a Point
  GeoDataFrame with `name` and `place` (tier) columns. Rendered with hierarchy
  in `PLACE_STYLE` — cities biggest, villages smallest. Frontend exposes four
  group toggles (cities / towns / suburbs / villages) mapped in `PLACE_GROUPS`.
- `road_labels`: highways with a `name` tag, deduplicated by name (each road
  drawn once at its representative point). Columns `name` and `tier` (major /
  minor). Frontend has master toggle plus a "include minor" option.

Master toggles are `style.show_place_labels` and `style.show_road_labels`; per-
tier toggles are `style.show_places_<group>` and
`style.show_road_labels_<tier>`. When a master toggle is off, the label layer
PNG is skipped in `layer_pngs` export.

The OSM attribution ("© OpenStreetMap contributors") is controlled by
`style.show_attribution` (default True). The ODbL requires attribution when
maps are shared or published, but not for private personal use.

## Style conventions

- Palette matches the reference posters: teal land, dark water, gold accents,
  off-white text.
- Layer rendering uses fixed z-order in `render.py`; changing it will
  reorder how layers cover each other in exports.
- Attribution ("© OpenStreetMap contributors") is drawn on every render.
  Do not remove it.

## Testing changes

- Test render changes with a synthetic GeoDataFrame first (see the example in
  `render.py`'s docstring). Public OSM APIs may be unavailable in a test
  environment.
- Test API changes with `app.app.test_client()`; you can prime `app.STATE`
  directly to skip the network call.
- When adding new marker shapes or layers, remember the frontend keeps the
  authoritative list of layer names in `LAYER_NAMES` in `static/app.js` and
  the backend in `LAYER_ORDER` in `mapstudio/render.py`; update both.
