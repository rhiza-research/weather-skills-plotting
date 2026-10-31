// A mediogram: at the grid cell nearest a point, a box of the forecast members
// (blue) beside a box of the model climate (red) for each lead, and the forecast
// mean as a line. Each box trace holds every member at every lead (.flat()), with the
// lead in days of each value (.flat('step')) as x, so Plotly draws one box per lead.
// EFM is the forecast's ensemble mean (summarize-dim --dim number).
// plot.py -i forecast.zarr=EF -i mclimate.zarr=MC -i forecast_mean.zarr=EFM --spec mediogram.jsonnet -o mediogram.png
local ws = import 'ws.libsonnet';
local inputs = std.extVar('inputs');
local pt = '.sel(lat=1.2, lon=10.8, method="nearest")';
local box(name, color, legend) = {
  type: 'box', name: legend, marker: { color: color }, boxpoints: false,
  x: '@%s.tp%s.flat("step")' % [name, pt], y: '@%s.tp%s.flat()' % [name, pt],
};
{
  data: [
    box('EF', '#1f4e9c', 'Forecast'),
    box('MC', '#c0392b', 'Model climate'),
    { type: 'scatter', mode: 'lines+markers', name: 'Forecast mean', line: { color: 'black', width: 2 },
      x: '@EFM.step.dt.days', y: '@EFM.tp' + pt },
  ],
  layout: {
    boxmode: 'group',
    title: { text: 'Rainfall at 1.2°N, 10.8°E, init %s' % ws.date(inputs.EF.coords.time) },
    xaxis: { title: { text: 'Lead (days)' }, dtick: 1 },
    yaxis: { title: { text: 'mm' }, rangemode: 'tozero' },
  },
}
