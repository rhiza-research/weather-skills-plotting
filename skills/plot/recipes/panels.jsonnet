// One map per forecast step in a grid, sharing one colorbar, with panel titles.
// plot.py -i forecast.zarr=FC --spec panels.jsonnet -o panels.png
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local bbox = inputs.FC.bbox;
local n = inputs.FC.dims.step;
local cols = 3;
{
  data: std.flattenArrays([
    [{ type: 'heatmap', x: '@FC.lon', y: '@FC.lat', z: '@FC.tp.isel(step=%d)' % i, coloraxis: 'coloraxis' } + ws.axes(i)]
    + ws.basemap(bbox, i, layers=['borders', 'coastline'])
    for i in std.range(0, n - 1)
  ]),
  layout: ws.grid(bbox, rows=std.ceil(n / cols), cols=cols) + {
    title: { text: 'Daily rainfall by lead, init %s' % inputs.FC.coords.time },
    coloraxis: ws.stepped(ws.palettes.ppt_daily),
    annotations: [ws.panelTitle(i, 'Day %d' % (i + 1)) for i in std.range(0, n - 1)],
  },
}
