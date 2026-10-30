// One variable against another, from one file (merge two files first), with year labels.
// plot.py -i index_vs_rain.zarr=IDX --spec scatter_xy.jsonnet -o scatter.png
{
  data: [
    { type: 'scatter', mode: 'markers+text', x: '@IDX.nino34', y: '@IDX.precip', text: '@IDX.time.dt.year',
      textposition: 'top center', marker: { size: 9 } },
  ],
  layout: {
    title: { text: 'Seasonal rainfall against Niño3.4' },
    xaxis: { title: { text: 'Niño3.4 anomaly (°C)' }, zeroline: true },
    yaxis: { title: { text: 'Rainfall (mm)' } },
    shapes: [{ type: 'line', x0: 0.5, x1: 0.5, yref: 'paper', y0: 0, y1: 1, line: { dash: 'dash', color: 'grey' } }],
  },
}
