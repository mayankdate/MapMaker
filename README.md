# Personal Map Studio

A local Python script that opens a browser tab for designing and exporting
printable, label-free street maps from OpenStreetMap data — the style used in
those city poster prints (Bombay / Baltimore / Boston etc.).

There is no server to deploy and no account to make. You run
`uv run python app.py`, the script starts a local web server on
`http://127.0.0.1:5000`, opens your browser to it, and you close the terminal
when you're done.

## What you can do

- Pan the map, search a city or address by name, or type coordinates.
- Draw a rectangle to define the print area (up to 35 km per side).
- Drop markers by clicking the map, from search results, or by exact latitude
  and longitude. Drag them to fine-tune, edit labels and coordinates in the
  sidebar.
- Pick a marker icon from the six built-in shapes (cross, dot, ring, star, pin,
  heart) or from any PNG you drop into `markers/`.
- Toggle each map layer (water, parks, buildings, rail, minor / major roads,
  paths) on or off, pick its color, adjust line width on the fly.
- Preview the styled poster in the sidebar. When you like it, export
  PNG (300 dpi) + PDF + SVG + per-layer GeoJSON + `settings.json` into
  `Outputs/<title>/`.

## Setup

You need [uv](https://docs.astral.sh/uv/); it installs the right Python
(`.python-version`) and the exact package versions in `uv.lock`:

```bash
uv sync
```

`geopandas` and its GIS libraries install from pre-built wheels, so no extra
system packages are needed.

## Run

```bash
uv run python app.py
```

Your browser opens `http://127.0.0.1:5000`. If it doesn't, open that URL
manually. Press `Ctrl+C` in the terminal to stop.

## Workflow inside the app

1. **Search or pan** to the neighborhood you want.
2. Use the rectangle tool (▢ icon, top-left of the map) to draw your print
   area. **The rectangle's shape becomes the print's shape** — draw wide for a
   landscape poster, tall for portrait.
3. Click **Fetch features for selected area**. First call for a new area hits
   OpenStreetMap and can take up to a minute; results are cached in
   `.osm_cache/` for later runs.
4. Add markers — three ways:
   - Type a place name in the search bar and click **+ Marker** next to a
     result.
   - Toggle **Click map to drop marker** and click anywhere.
   - Click **Add by coordinates…** for exact lat/lon.
5. Pick a per-marker icon in the row's dropdown, or set a default icon at the
   top of the Markers section so every new marker uses it.
6. In the **Layers** section, toggle layers on/off and adjust line widths.
7. In **Text labels**, turn on place labels and/or road names if you want any.
   Place labels have a hierarchy (cities → towns → suburbs/neighbourhoods →
   villages/hamlets) — tick just the tiers you want. Road names default to
   major roads only; there's an option to include minor roads too.
8. In **Colors & page**, tweak the palette, title, and the **long edge** in
   inches. The other dimension is derived from the rectangle you drew — the
   hint below shows the final print size. There's also an
   "Include OpenStreetMap attribution" checkbox here.
9. Click **Render preview** to see the styled poster inline.
10. In **Export**, tick the formats you want and click **Export to Outputs/**.
    Files land in `Outputs/<slugified-title>/`.

## Export formats

Pick any combination:

- **Combined PNG** — 300 dpi flat image; the finished poster.
- **Combined PDF** / **SVG** — vector versions, editable in
  Illustrator / Inkscape / Affinity.
- **Per-layer PNGs** — one 300 dpi transparent PNG per visible map layer
  (`background.png`, `water.png`, `major.png`, …, `markers.png`,
  `labels.png`). All share the exact same dimensions, so importing them into
  Procreate or Photoshop as separate layers reproduces the map — and lets you
  restyle any single layer non-destructively.
- **Per-layer GeoJSON** — raw vector features per layer, for opening in QGIS
  or any GIS tool.

`markers.geojson` and `settings.json` are always written alongside so you can
reproduce the export or edit markers externally.

## Where things live

```text
app.py                        The script you run.
mapstudio/fetch.py            OpenStreetMap fetch and layer classification.
mapstudio/render.py           matplotlib rendering (this is the poster look).
mapstudio/defaults.py         Generates the six default marker PNGs on first run.
templates/index.html          The single-page UI.
static/app.js, static/style.css  Frontend.
markers/                      Drop your own transparent PNG icons here.
assets/default_markers/       Built-in marker shapes; regenerated if deleted.
Outputs/<title>/              Exports: PNG, PDF, SVG, layers/, markers.geojson, settings.json.
.osm_cache/                   OSMnx cache — safe to delete anytime.
```

## Custom marker icons

Drop transparent-background PNGs into `markers/` (square, 128 px or bigger is
plenty). Reload the page and they appear in the icon grid and in every
marker's icon dropdown. Filenames are shown as labels, so name them clearly
(`home.png`, `cafe.png`).

## Reproducing an export

Every export writes `settings.json` alongside the images, including the full
bounding box, palette, layer visibility, marker list, and page size. Reopen it
later to re-render the same map after editing markers.

## Attribution

Map data is © OpenStreetMap contributors, available under the
[Open Database License](https://www.openstreetmap.org/copyright).

The "Include OpenStreetMap attribution" checkbox in the Colors & page section
controls whether the credit is drawn on the export. **Turn it off freely for
personal prints you keep for yourself.** If you share, publish, or sell prints
made with this tool, ODbL requires you to credit OpenStreetMap somewhere
visible — either back on the print itself, or in accompanying text /
description / caption.

## About OSM coverage

The map data comes from OpenStreetMap, which is community-edited. In some
regions (especially Western Europe, most of the US, large cities in general)
coverage is comparable to Google Maps or better. In others — including
several Mumbai suburbs — Google's paid data is more complete. This is a
fundamental trade-off of using free vector data that can be restyled: Google
doesn't offer their vector features via any free API, only pre-rendered
tiles you can't restyle. If the render looks sparse for an area, you can
either draw a different rectangle, or (properly) contribute the missing
detail to OSM at [openstreetmap.org/edit](https://www.openstreetmap.org/edit).
