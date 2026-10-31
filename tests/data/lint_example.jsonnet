// A style-only figure spec: every data value is an @reference that a trusted
// step fills in later, so nothing here can introduce numbers of its own.
// Jsonnet still does the repetitive work: one panel per station, shared styles.
//
//   check_bindings(_jsonnet.evaluate_file('example.jsonnet'))  # from plotly_ref_lint
local stations = ['nairobi', 'mombasa', 'kisumu'];

local ink = { primary: '#0b0b0b', secondary: '#52514e', grid: '#e4e3df', surface: '#fcfcfb' };
local axis = { gridcolor: ink.grid, linecolor: ink.grid, zeroline: false, tickfont: { color: ink.secondary } };
local line(color, width) = { mode: 'lines', line: { color: color, width: width } };

// Panel i (1-based) of n, stacked top to bottom.
local domain(i, n) = [1 - i / n + 0.06, 1 - (i - 1) / n];
local suffix(i) = if i == 1 then '' else std.toString(i);

local panel(i, station) = {
  traces: [
    line('#2a78d6', 1) {
      type: 'scatter',
      name: 'Daily',
      legendgroup: 'daily',
      showlegend: i == 1,
      x: '@%s/time' % station,
      y: '@%s/t2m' % station,
      xaxis: 'x' + suffix(i),
      yaxis: 'y' + suffix(i),
      opacity: 0.6,
      hovertemplate: '%{y:.1f} °C<extra>' + station + '</extra>',
    },
    line('#eb6834', 2) {
      type: 'scatter',
      name: '7-day mean',
      legendgroup: 'mean',
      showlegend: i == 1,
      x: '@%s/time' % station,
      y: '@%s/t2m_7d_mean' % station,
      xaxis: 'x' + suffix(i),
      yaxis: 'y' + suffix(i),
    },
  ],
  axes: {
    ['xaxis' + suffix(i)]: axis { anchor: 'y' + suffix(i), matches: 'x', showticklabels: i == std.length(stations) },
    ['yaxis' + suffix(i)]: axis { domain: domain(i, std.length(stations)), title: { text: '°C' } },
  },
  title: {
    text: std.asciiUpper(station[0]) + station[1:],
    xref: 'paper',
    yref: 'paper',
    x: 0,
    y: domain(i, std.length(stations))[1],
    xanchor: 'left',
    yanchor: 'bottom',
    showarrow: false,
    font: { color: ink.primary },
  },
};

local panels = [panel(i + 1, stations[i]) for i in std.range(0, std.length(stations) - 1)];

{
  data: std.flattenArrays([p.traces for p in panels]),
  layout: std.foldl(function(acc, p) acc + p.axes, panels, {}) {
    title: { text: 'Air temperature by station', x: 0, xref: 'paper' },
    font: { family: 'Inter, system-ui, sans-serif', color: ink.secondary },
    paper_bgcolor: ink.surface,
    plot_bgcolor: ink.surface,
    height: 720,
    hovermode: 'x unified',
    legend: { orientation: 'h', x: 1, xanchor: 'right', y: 1.02, yanchor: 'bottom' },
    annotations: [p.title for p in panels],
    // A freezing line drawn across every panel: on a data axis, so its y is a reference too.
    shapes: [
      { type: 'line', xref: 'x' + suffix(i) + ' domain', x0: 0, x1: 1, yref: 'y' + suffix(i), y0: '@const/freezing_c', y1: '@const/freezing_c', line: { color: ink.secondary, dash: 'dot', width: 1 } }
      for i in std.range(1, std.length(stations))
    ],
  },
}
