// A sea-level pressure chart: isobars every 4 hPa with labels, and H / L at the
// centres with their central pressure. HI and LO come from local-extrema --kind high
// and --kind low on the same one-time map, in hPa (unit-convert msl first).
// plot.py -i msl_hpa.zarr=MSL -i highs.zarr=HI -i lows.zarr=LO --spec mslp.jsonnet -o mslp.png
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local bbox = inputs.MSL.bbox;
local centres(name, letter, color) = {
  type: 'scatter', mode: 'text', x: '@%s.lon' % name, y: '@%s.lat' % name, showlegend: false,
  customdata: '@%s.msl' % name, texttemplate: '<b>' + letter + '</b><br>%{customdata:.0f}',
  textfont: { color: color, size: 16 }, cliponaxis: false,
};
{
  data: [
    { type: 'contour', x: '@MSL.lon', y: '@MSL.lat', z: '@MSL.msl.squeeze()', showscale: false, showlegend: false,
      contours: { coloring: 'none', showlabels: true, start: 900, end: 1100, size: 4 }, line: { color: 'black', width: 1 } },
    centres('HI', 'H', '#1f4e9c'),
    centres('LO', 'L', '#c0392b'),
  ] + ws.basemap(bbox, layers=['borders', 'coastline']),
  layout: ws.map(bbox) + { title: { text: 'Sea-level pressure (hPa)' } },
}
