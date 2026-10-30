// Wind speed shading with quiver arrows, each as long as its wind is strong.
// WD comes from wind-speed-direction --arrow-scale DEG_PER_UNIT --arrow-step CELLS:
// wind_speed, plus arrow_x / arrow_y, every arrow's shaft and head as line segments in
// map degrees (DEG_PER_UNIT long per unit of speed, one arrow every CELLS grid cells),
// drawn here as one lines trace.
// plot.py -i wind_sd.zarr=WD --spec wind.jsonnet -o wind.png
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local bbox = inputs.WD.bbox;
local t = '.isel(time=0)';
{
  data: [
    { type: 'heatmap', x: '@WD.lon', y: '@WD.lat', z: '@WD.wind_speed' + t, colorscale: 'YlGnBu',
      colorbar: { title: { text: 'm/s' } } },
    { type: 'scatter', mode: 'lines', x: '@WD.arrow_x' + t, y: '@WD.arrow_y' + t,
      line: { color: 'black', width: 1 }, hoverinfo: 'skip', showlegend: false },
  ] + ws.basemap(bbox, rivers=false, admin1=false),
  layout: ws.map(bbox) + { title: { text: '10 m wind, %s' % ws.date(inputs.WD.coords.time[0]) } },
}
