// A vertical section between two places: a field shaded over points along the line and
// pressure, with the horizontal wind at each point and level as arrows (north up, turned
// to the direction it blows from, as long as it is strong).
// Data steps first: point-value samples the grid at points along the line
// (--points-csv with lat,lon,id,name rows in order from one end to the other), and
// wind-speed-direction turns that file's u / v into wind_speed and wind_from_direction.
// Pick one time first (select). The points are a category axis in file order, so the
// line can run in any direction; the first and last point names label the ends.
// ERA5 calls the pressure dim `level`; other files call it `vertical`: change `lev`.
// Levels under high ground hold values from below the surface; say so in the caption.
// plot.py -i section.zarr=SEC -i section_wind.zarr=SW --spec transect.jsonnet -o transect.png
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local lev = 'level';
local names = inputs.SEC.coords.name;
local field = 'specific_humidity';
// 1000 to 100 hPa. ERA5 stores levels ascending; a file stored from 1000 down takes slice(1000, 100).
local levels = '.sel(%s=slice(100, 1000))' % lev;
// Every other level gets arrows; 10 m/s is an arrow 2 * 10 * scale px long.
local thin = levels + '.isel(%s=slice(None, None, 2))' % lev;
local scale = 1.25;
local speed = '@SW.wind_speed' + thin + '.flat()';
local from = '@SW.wind_from_direction' + thin + '.flat()';
local at = {
  type: 'scatter', mode: 'markers', hoverinfo: 'skip', showlegend: false, cliponaxis: false,
  x: '@SW.wind_speed' + thin + '.flat("station_id")', y: '@SW.wind_speed' + thin + '.flat("%s")' % lev,
};
{
  data: [
    { type: 'contour', x: '@SEC.station_id', y: '@SEC.%s%s' % [lev, levels],
      z: '@SEC.%s%s.transpose("%s", "station_id")' % [field, levels, lev],
      colorscale: 'YlGnBu', contours: { coloring: 'fill', showlabels: true },
      colorbar: { title: { text: inputs.SEC.vars[field].units } } },
    at { marker: { symbol: 'line-ns', size: speed + ' * %g' % (scale / 0.7), angle: from,
                   line: { width: 1.3, color: 'black' } } },
    at { marker: { symbol: 'arrow-down', color: 'black', angle: from, standoff: speed + ' * %g' % scale,
                   size: 4 } },
  ],
  layout: {
    width: 900, height: 600,
    title: { text: '%s → %s, %s' % [names[0], names[std.length(names) - 1], ws.date(inputs.SEC.coords.time)],
             subtitle: { text: 'Shading: %s (%s). Arrows: horizontal wind, north up' % [std.get(inputs.SEC.vars[field], 'long_name', field), inputs.SEC.vars[field].units] } },
    // Category axis: one column per point, in file order. A linear pressure axis keeps
    // the lower levels apart (a log axis crowds 700–1000 hPa).
    xaxis: { title: { text: 'Points along the line' }, type: 'category', showticklabels: false },
    yaxis: { title: { text: 'Pressure (hPa)' }, range: [1000, 100], dtick: 100 },
    annotations: [
      { text: names[0], xref: 'paper', yref: 'paper', x: 0, y: -0.02, xanchor: 'left', yanchor: 'top', showarrow: false },
      { text: names[std.length(names) - 1], xref: 'paper', yref: 'paper', x: 1, y: -0.02, xanchor: 'right', yanchor: 'top', showarrow: false },
    ],
  },
}
