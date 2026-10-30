// Wind speed shading with an arrow (shaft and head) on every 2nd cell, all one length.
// wind_speed and wind_from_direction come from the wind-speed-direction skill.
// Each arrow is two Plotly markers centred on the cell, turned to the from-direction:
// a line-ns shaft (Plotly draws it 1.4 times its size long) and an arrow-down head,
// whose tip is at the cell, moved half the length downwind with standoff so it
// ends where the shaft does.
// plot.py -i wind_sd.zarr=WD --spec wind.jsonnet -o wind.png
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local bbox = inputs.WD.bbox;
local sel = '.isel(time=0)';
local thin = '.isel(time=0, lat=slice(None, None, 2), lon=slice(None, None, 2))';
local length = 16;  // arrow length, px; every arrow is this long
local at = {
  type: 'scatter', mode: 'markers', hoverinfo: 'skip', showlegend: false, cliponaxis: false,
  x: '@WD.wind_speed' + thin + '.flat("lon")', y: '@WD.wind_speed' + thin + '.flat("lat")',
};
{
  data: [
    { type: 'heatmap', x: '@WD.lon', y: '@WD.lat', z: '@WD.wind_speed' + sel, colorscale: 'YlGn',
      colorbar: { title: { text: 'm/s' } } },
    at { marker: { symbol: 'line-ns', size: length / 1.4, line: { width: 1.5, color: 'black' },
                   angle: '@WD.wind_from_direction' + thin + '.flat()' } },
    at { marker: { symbol: 'arrow-down', size: 8, color: 'black', standoff: length / 2,
                   angle: '@WD.wind_from_direction' + thin + '.flat()' } },
  ] + ws.basemap(bbox),
  layout: ws.map(bbox) + { title: { text: '10 m wind' } },
}
