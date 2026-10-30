// Wind speed shading with arrows on every 2nd cell, each as long as its wind is
// strong: 2 px per unit of speed (20 px for 10 m/s). wind_speed and
// wind_from_direction come from the wind-speed-direction skill.
// Each arrow is two Plotly markers centred on the cell, turned to the from-direction:
// a line-ns shaft whose size is the speed (sizeref 0.7 makes its half-length 1 px per
// unit), and an arrow-down head whose tip is moved downwind by standoff = the speed
// in px, so it ends where the shaft does. Run unit-convert on the speed (knots, km/h)
// for longer arrows.
// plot.py -i wind_sd.zarr=WD --spec wind.jsonnet -o wind.png
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local bbox = inputs.WD.bbox;
local sel = '.isel(time=0)';
local thin = '.isel(time=0, lat=slice(None, None, 2), lon=slice(None, None, 2))';
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
    at { marker: { symbol: 'line-ns', size: speed, sizemode: 'diameter', sizeref: 0.7, angle: from,
                   line: { width: 1.5, color: 'black' } } },
    at { marker: { symbol: 'arrow-down', size: 7, color: 'black', standoff: speed, angle: from } },
  ] + ws.basemap(bbox),
  layout: ws.map(bbox) + { title: { text: '10 m wind' } },
}
