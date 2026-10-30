// A mediogram: at the grid cell nearest a point, a box of the forecast members
// (blue) beside a box of the model climate (red) for each lead, and the forecast
// mean as a line. EFM is the forecast's ensemble mean (summarize-dim --dim number).
// plot.py -i forecast.zarr=EF -i mclimate.zarr=MC -i forecast_mean.zarr=EFM --spec mediogram.jsonnet -o mediogram.png
local inputs = std.extVar('inputs');
local pt = '.sel(lat=1.2, lon=10.8, method="nearest")';
local leads = inputs.EF.coords.step;  // lead days
local label(k) = 'Day %g' % leads[k];
local box(name, k, color, legend) = {
  type: 'box', y: '@%s.tp%s.isel(step=%d)' % [name, pt, k], x0: label(k), name: legend,
  offsetgroup: name, legendgroup: name, showlegend: k == 0, marker: { color: color }, boxpoints: false,
};
{
  data: std.flattenArrays([
    [box('EF', k, '#1f4e9c', 'Forecast'), box('MC', k, '#c0392b', 'Model climate')]
    for k in std.range(0, std.length(leads) - 1)
  ]) + [
    { type: 'scatter', mode: 'lines+markers', name: 'Forecast mean', line: { color: 'black', width: 2 },
      x: [label(k) for k in std.range(0, std.length(leads) - 1)], y: '@EFM.tp%s' % pt },
  ],
  layout: {
    boxmode: 'group',
    title: { text: 'Rainfall at 1.2°N, 10.8°E, init %s' % inputs.EF.coords.time },
    yaxis: { title: { text: 'mm' }, rangemode: 'tozero' },
  },
}
