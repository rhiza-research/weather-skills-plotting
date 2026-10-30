// Station dots over a grid, both on one colorbar, each dot labelled with its id.
// plot.py -i rain.zarr=OBS -i stations.zarr=STN --spec stations.jsonnet -o stations.png
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local bbox = inputs.OBS.bbox;
local day = '.isel(time=0)';
{
  data: [
    { type: 'heatmap', x: '@OBS.lon', y: '@OBS.lat', z: '@OBS.precip' + day, coloraxis: 'coloraxis' },
    { type: 'scatter', mode: 'markers+text', name: 'Stations', x: '@STN.lon', y: '@STN.lat',
      text: '@STN.point_id', textposition: 'top center',
      marker: { size: 12, color: '@STN.precip' + day, coloraxis: 'coloraxis', line: { color: 'black', width: 1 } } },
  ] + ws.basemap(bbox),
  layout: ws.map(bbox) + {
    title: { text: 'Gridded rain and station gauges' },
    coloraxis: ws.stepped(ws.palettes.ppt_daily) + { colorbar+: { title: { text: 'mm/day' } } },
  },
}
