// A vertical cross-section: a field over longitude and pressure, 1000 hPa at the bottom.
// Pick every other dim first: here one forecast step and the latitude nearest 1°S.
// Levels under high ground hold values from below the surface; say so in the caption.
// plot.py -i rh.zarr=RH --spec cross_section.jsonnet -o section.png
local inputs = std.extVar('inputs');
local levels = '.sel(vertical=slice(1000, 100))';
local pick = '.isel(step=0).sel(lat=-1, method="nearest")';
{
  data: [
    { type: 'contour', x: '@RH.lon', y: '@RH.vertical' + levels,
      z: '@RH.r' + pick + levels + '.transpose("vertical", "lon")',
      colorscale: 'BrBG', zmin: 0, zmax: 100, contours: { coloring: 'fill', showlabels: true, start: 0, end: 100, size: 10 },
      colorbar: { title: { text: '%' } } },
  ],
  layout: {
    title: { text: 'Relative humidity along 1°S, %s' % (import 'ws.libsonnet').date(inputs.RH.coords.time) },
    xaxis: { title: { text: 'Longitude' }, ticksuffix: '°' },
    // A log pressure axis labels only the levels, not Plotly's minor ticks.
    yaxis: { title: { text: 'Pressure (hPa)' }, type: 'log', autorange: 'reversed', tickvals: '@RH.vertical' + levels },
  },
}
