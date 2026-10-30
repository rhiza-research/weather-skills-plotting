// One map: a grid on a stepped palette, a region outline and the base map.
// plot.py -i rain_week.zarr=OBS -i kenya.geojson=KENYA --spec map.jsonnet -o map.png
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local bbox = inputs.KENYA.bbox;  // or {n: 5.5, w: 33.5, s: -5, e: 42.5}
local t = inputs.OBS.coords.time;
{
  data: [
    { type: 'heatmap', x: '@OBS.lon', y: '@OBS.lat', z: '@OBS.precip.isel(time=0)', coloraxis: 'coloraxis' },
    { type: 'scatter', mode: 'lines', x: '@KENYA.x', y: '@KENYA.y', line: { color: 'black', width: 2 },
      hoverinfo: 'skip', showlegend: false },
  ] + ws.basemap(bbox),
  layout: ws.map(bbox) + {
    template: ws.template,
    title: { text: 'Rainfall, week of %s' % t[0] },
    coloraxis: ws.stepped(ws.palettes.ppt_week) + { colorbar+: { title: { text: 'mm' } } },
  },
}
