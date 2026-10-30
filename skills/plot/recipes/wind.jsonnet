// Wind speed shading with arrows on every 2nd cell. wind_speed and wind_to_direction
// come from the wind-speed-direction skill. Arrows are Plotly arrow markers.
// plot.py -i wind_sd.zarr=WD --spec wind.jsonnet -o wind.png
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local bbox = inputs.WD.bbox;
local sel = '.isel(time=0)';
local thin = '.isel(time=0, lat=slice(None, None, 2), lon=slice(None, None, 2))';
{
  data: [
    { type: 'heatmap', x: '@WD.lon', y: '@WD.lat', z: '@WD.wind_speed' + sel, colorscale: 'YlGn',
      colorbar: { title: { text: 'm/s' } } },
    { type: 'scatter', mode: 'markers', hoverinfo: 'skip', showlegend: false,
      x: '@WD.wind_speed' + thin + '.flat("lon")', y: '@WD.wind_speed' + thin + '.flat("lat")',
      marker: { symbol: 'arrow', color: 'black', sizemode: 'diameter', sizeref: 0.5,
                size: '@WD.wind_speed' + thin + '.flat()', angle: '@WD.wind_to_direction' + thin + '.flat()' } },
  ] + ws.basemap(bbox),
  layout: ws.map(bbox) + { title: { text: '10 m wind' } },
}
