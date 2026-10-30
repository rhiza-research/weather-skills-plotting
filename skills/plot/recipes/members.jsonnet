// Ensemble members as thin grey lines with the ensemble mean in bold, at the grid
// cell nearest a point. The mean comes from summarize-dim --dim number --method mean.
// plot.py -i forecast.zarr=ENS -i forecast_mean.zarr=MEAN --spec members.jsonnet -o members.png
local inputs = std.extVar('inputs');
local pt = '.sel(lat=1.2, lon=10.8, method="nearest")';
{
  data: [
    { type: 'scatter', mode: 'lines', x: '@ENS.time', y: '@ENS.tp%s.isel(number=%d)' % [pt, m],
      line: { color: 'grey', width: 0.7 }, legendgroup: 'members', showlegend: m == 0, name: 'Members' }
    for m in std.range(0, inputs.ENS.dims.number - 1)
  ] + [
    { type: 'scatter', mode: 'lines', x: '@MEAN.time', y: '@MEAN.tp' + pt, name: 'Mean', line: { color: 'red', width: 3 } },
  ],
  layout: {
    title: { text: 'Ensemble rainfall at 1.2°N, 10.8°E' },
    yaxis: { title: { text: 'mm/day' }, rangemode: 'tozero' },
  },
}
