// A grid with diagonal hatching over the cells a 0/1 mask flags (onset already observed,
// a significant change, 2 of 3 models agreeing). Plotly heatmaps have no pattern fill, so
// each hatched cell gets a line-ne marker as big as the cell: neighbouring strokes join
// into continuous lines. The mask colours the strokes, 1 dark and 0 clear, so no data
// step is needed beyond the mask itself. Each stroke is drawn twice, dark and wide under
// light and thin, so it shows on dark and light colours alike.
// MASK must be 0 or 1 in every cell: a NaN cell draws a grey stroke. Make it with
// `indicator --rule` on a field that has a value in every cell of the box (clip the
// field after, not before), and outline a region with a GeoJSON line rather than
// clipping the mask. MASK and the field share one grid.
// plot.py -i rain_week.zarr=OBS -i flag.zarr=MASK --spec hatch.jsonnet -o hatch.png
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local bbox = inputs.OBS.bbox;
local layout = ws.map(bbox);
// About 40 strokes across the map; each stroke spans `step` cells.
local across = 40;
local step = std.max(1, std.ceil(inputs.MASK.dims.longitude / across));
local cell = (layout.width - layout.margin.l - layout.margin.r) * step / inputs.MASK.dims.longitude;
// time=0: the same date as the field; leave it out for a mask with no time dim.
local thin = '.isel(time=0, lat=slice(None, None, %d), lon=slice(None, None, %d))' % [step, step];
local flag = '@MASK.indicator' + thin;
local hatch(color, width) = {
  type: 'scatter', mode: 'markers', hoverinfo: 'skip', showlegend: false,
  x: flag + '.flat("lon")', y: flag + '.flat("lat")',
  marker: { symbol: 'line-ne', size: cell, line: { width: width, color: flag + '.flat()',
            colorscale: [[0, 'rgba(0,0,0,0)'], [1, color]], cmin: 0, cmax: 1 } },
};
{
  data: [
    { type: 'heatmap', x: '@OBS.lon', y: '@OBS.lat', z: '@OBS.precip.isel(time=0)', coloraxis: 'coloraxis' },
    hatch('black', 2.5),
    hatch('white', 1),
  ] + ws.basemap(bbox, rivers=false, admin=false),
  layout: layout + ws.classBar(ws.palettes.ppt_week, 'mm') + {
    title: { text: 'Rainfall, week of %s (hatched: flagged cells)' % ws.date(inputs.OBS.coords.time[0]) },
  },
}
