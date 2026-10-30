// A vertical cross-section: a field over longitude and pressure, 1000 hPa at the bottom.
// Pick every other dim first (here one latitude).
// plot.py -i rh.zarr=RH --spec cross_section.jsonnet -o section.png
{
  data: [
    { type: 'contour', x: '@RH.lon', y: '@RH.vertical', z: '@RH.r.sel(lat=-1, method="nearest").transpose("vertical", "lon")',
      colorscale: 'BrBG', contours: { coloring: 'fill', showlabels: true }, colorbar: { title: { text: '%' } } },
  ],
  layout: {
    title: { text: 'Relative humidity along 1°S' },
    xaxis: { title: { text: 'Longitude' }, ticksuffix: '°' },
    yaxis: { title: { text: 'Pressure (hPa)' }, type: 'log', autorange: 'reversed' },
  },
}
