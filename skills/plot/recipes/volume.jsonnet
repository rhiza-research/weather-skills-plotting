// A 3-D scene: a field on pressure levels drawn as a surface of one value (an isosurface)
// above the ground, played through the forecast steps. The ground is a surface at the
// surface pressure, so it sits on the same pressure axis as the levels (in hPa).
// .flat() lays the level × lat × lon block out as one point per cell, the same order
// for value and each coordinate. Frame k replaces only the isosurface (trace 1).
// Name the level dim as your file does (vertical here; often pressure or level).
// plot.py -i rh.zarr=RH -i sp.zarr=SP --spec volume.jsonnet -o rh3d.html
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local bbox = inputs.RH.bbox;
local leads = inputs.RH.coords.step;
local block(k) = '@RH.r.isel(step=%d)' % k;
local label(k) = '+%g h' % (leads[k] * 24);
local level = 80;
local iso(k) = {
  type: 'isosurface', value: block(k) + '.flat()',
  // One surface at exactly isomin: with isomin < isomax a single surface sits halfway between.
  isomin: level, isomax: level, surface: { count: 1 },
  colorscale: [[0, '#4a7fb5'], [1, '#4a7fb5']], showscale: false, opacity: 0.5,
  caps: { x: { show: false }, y: { show: false }, z: { show: false } },
  name: 'RH %g%%' % level,
};
{
  data: [
    { type: 'surface', x: '@SP.lon', y: '@SP.lat', z: '@SP.sp.isel(step=0)',
      colorscale: [[0, '#8a7a6c'], [1, '#c9d7a8']], showscale: false, name: 'ground' },
    iso(0) + { x: block(0) + '.flat("lon")', y: block(0) + '.flat("lat")', z: block(0) + '.flat("vertical")' },
  ],
  frames: [
    { name: label(k), traces: [1], data: [iso(k)], layout: { title: { text: 'Relative humidity %g%%, %s' % [level, label(k)] } } }
    for k in std.range(0, std.length(leads) - 1)
  ],
  layout: ws.player([label(k) for k in std.range(0, std.length(leads) - 1)]) + {
    title: { text: 'Relative humidity %g%%, %s' % [level, label(0)] },
    scene: {
      xaxis: { title: { text: 'Longitude' } },
      yaxis: { title: { text: 'Latitude' } },
      zaxis: { title: { text: 'Pressure (hPa)' }, autorange: 'reversed' },
      // Degrees equal on x and y; the vertical squashed to half the width.
      aspectmode: 'manual',
      aspectratio: { x: 1, y: (bbox.n - bbox.s) / (bbox.e - bbox.w), z: 0.5 },
    },
  },
}
