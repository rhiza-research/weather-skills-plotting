// A map played through time: one frame per time, play / pause and a slider in HTML,
// the same frames as a looping .gif. Frame k replaces trace 0 (the field). A scatter
// trace that changes in the frames (wind arrows, storm tracks) must be scattergl: an
// SVG scatter in a frame blanks the heatmap on every other paint.
// plot.py -i rain_daily.zarr=OBS --spec animation.jsonnet -o rain.html -o rain.gif
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local bbox = inputs.OBS.bbox;
local times = inputs.OBS.coords.time;
local field(k) = { type: 'heatmap', x: '@OBS.lon', y: '@OBS.lat', z: '@OBS.precip.isel(time=%d)' % k, coloraxis: 'coloraxis' };
{
  data: [field(0)] + ws.basemap(bbox),
  frames: [
    { name: ws.date(times[k]), traces: [0], data: [field(k)], layout: { title: { text: 'Rainfall ' + ws.date(times[k]) } } }
    for k in std.range(0, std.length(times) - 1)
  ],
  layout: ws.map(bbox) + ws.player([ws.date(t) for t in times], duration=500) + ws.classBar(ws.palettes.ppt_daily, 'mm') + {
    title: { text: 'Rainfall ' + ws.date(times[0]) },
  },
}
