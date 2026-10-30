// Wind speed shading with arrows on every 3rd cell, each as long as its wind is strong.
// wind_speed and wind_from_direction come from the wind-speed-direction skill.
// Each arrow is two Plotly markers centred on the cell, turned to the from-direction:
// a line-ns shaft and an arrow-down head whose tip is moved downwind by standoff.
// Plotly draws line-ns 1.4 times its size long, so shaft size = speed * scale / 0.7
// and head standoff = speed * scale put the head tip on the shaft end; the arrow is
// 2 * scale px long per unit of speed. Heads grow with the arrow, down to a minimum.
// plot.py -i wind_sd.zarr=WD --spec wind.jsonnet -o wind.png
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local bbox = inputs.WD.bbox;
local sel = '.isel(time=0)';
local thin = '.isel(time=0, lat=slice(None, None, 3), lon=slice(None, None, 3))';
local scale = 2;  // px per unit of speed, each side of the cell: 10 m/s draws a 40 px arrow
local speed = '@WD.wind_speed' + thin + '.flat()';
local from = '@WD.wind_from_direction' + thin + '.flat()';
local at = {
  type: 'scatter', mode: 'markers', hoverinfo: 'skip', showlegend: false, cliponaxis: false,
  x: '@WD.wind_speed' + thin + '.flat("lon")', y: '@WD.wind_speed' + thin + '.flat("lat")',
};
{
  data: [
    { type: 'heatmap', x: '@WD.lon', y: '@WD.lat', z: '@WD.wind_speed' + sel, colorscale: 'YlGn',
      colorbar: { title: { text: 'm/s' } } },
    at { marker: { symbol: 'line-ns', size: speed + ' * %g' % (scale / 0.7), angle: from,
                   line: { width: 1.3, color: 'black' } } },
    at { marker: { symbol: 'arrow-down', color: 'black', angle: from, standoff: speed + ' * %g' % scale,
                   size: speed + ' * %g' % (0.5 * scale), sizemin: 4 } },
  ] + ws.basemap(bbox, rivers=false, admin1=false),
  layout: ws.map(bbox) + { title: { text: '10 m wind' } },
}
