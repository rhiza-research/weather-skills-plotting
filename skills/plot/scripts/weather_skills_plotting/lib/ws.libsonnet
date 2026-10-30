// Helpers for plot specs. Every function returns plain Plotly JSON (or @ reference
// strings inside it); override any key with +, e.g. ws.map(bbox) + {height: 600}.
//
// bbox is {n, w, s, e} in degrees, as inputs.NAME.bbox gives it.
local palettes = import 'palettes.libsonnet';

local round(x) = std.floor(x + 0.5);

// Margins (px) around the plotting area: room for the title, ticks and a colorbar.
local margin = { l: 50, r: 110, t: 70, b: 45 };

// Natural Earth scale for a map span, and whether provinces / counties are readable.
local scaleFor(bbox) =
  local span = std.max(bbox.e - bbox.w, bbox.n - bbox.s);
  if span > 90 then '110m' else if span > 45 then '50m' else '10m';

// Base-map line styles, drawn bottom first.
local basemapStyles = {
  admin1: { line: { color: '#737373', width: 0.6 } },
  rivers: { line: { color: '#708090', width: 0.6 } },
  lakes: { line: { color: '#708090', width: 0.4 }, fill: 'toself', fillcolor: '#708090' },
  borders: { line: { color: '#262626', width: 1.2 } },
  disputed: { line: { color: '#404040', width: 1, dash: '4px,3px' } },
  coastline: { line: { color: 'black', width: 1.2 } },
};

{
  palettes: palettes,

  // The house Plotly template: colorway and box outlines.
  template: {
    layout: {
      colorway: ['#4c72b0', '#dd8452', '#55a868', '#c44e52', '#8172b3', '#937860', '#da8bc3', '#8c8c8c', '#ccb974', '#64b5cd'],
      shapedefaults: { fillcolor: 'rgba(0,0,0,0)', opacity: 1, line: { width: 2, color: '#333333' } },
    },
  },

  // Panel i's axis names (0 → x / y, 1 → x2 / y2, …), to add to a trace.
  axes(i):: {
    xaxis: if i == 0 then 'x' else 'x%d' % (i + 1),
    yaxis: if i == 0 then 'y' else 'y%d' % (i + 1),
  },

  // One map: lon/lat axes on the bbox with equal degrees, and a canvas sized to its aspect.
  map(bbox, width=760):: {
    local plotw = width - margin.l - margin.r,
    width: width,
    height: round(plotw * (bbox.n - bbox.s) / (bbox.e - bbox.w)) + margin.t + margin.b,
    margin: margin,
    xaxis: { range: [bbox.w, bbox.e], showgrid: false, zeroline: false, ticksuffix: '°', constrain: 'domain' },
    yaxis: {
      range: [bbox.s, bbox.n], showgrid: false, zeroline: false, ticksuffix: '°',
      scaleanchor: 'x', scaleratio: 1, constrain: 'domain',
    },
  },

  // Maps in a grid, filled row by row from the top left: panel i is ws.axes(i).
  // Tick labels show on the bottom row (longitude) and left column (latitude).
  grid(bbox, rows, cols, panel=340, gap=0.04):: {
    local aspect = (bbox.n - bbox.s) / (bbox.e - bbox.w),
    width: cols * panel + margin.l + margin.r,
    height: round(rows * panel * aspect / (1 - gap)) + margin.t + margin.b,
    margin: margin,
  } + {
    [if i == 0 then 'xaxis' else 'xaxis%d' % (i + 1)]: {
      local c = i % cols,
      local r = std.floor(i / cols),
      domain: [c / cols + gap / 2, (c + 1) / cols - gap / 2],
      range: [bbox.w, bbox.e], showgrid: false, zeroline: false, ticksuffix: '°',
      constrain: 'domain', showticklabels: r == rows - 1,
      anchor: if i == 0 then 'y' else 'y%d' % (i + 1),
    }
    for i in std.range(0, rows * cols - 1)
  } + {
    [if i == 0 then 'yaxis' else 'yaxis%d' % (i + 1)]: {
      local c = i % cols,
      local r = std.floor(i / cols),
      domain: [1 - (r + 1) / rows + gap / 2, 1 - r / rows - gap / 2],
      range: [bbox.s, bbox.n], showgrid: false, zeroline: false, ticksuffix: '°',
      scaleanchor: if i == 0 then 'x' else 'x%d' % (i + 1), scaleratio: 1,
      constrain: 'domain', showticklabels: c == 0,
      anchor: if i == 0 then 'x' else 'x%d' % (i + 1),
    }
    for i in std.range(0, rows * cols - 1)
  },

  // A title above panel i, as a layout annotation.
  panelTitle(i, text):: {
    text: text, showarrow: false, font: { size: 13 },
    xref: (if i == 0 then 'x' else 'x%d' % (i + 1)) + ' domain', x: 0.5, xanchor: 'center',
    yref: (if i == 0 then 'y' else 'y%d' % (i + 1)) + ' domain', y: 1.01, yanchor: 'bottom',
  },

  // Coastlines, borders, lakes and (on country-sized maps) admin-1 lines from the
  // built-in Natural Earth input NE, clipped to bbox, on panel i.
  // layers lists which to draw; style overrides a layer's Plotly keys.
  basemap(bbox, i=0, layers=null, style={}):: [
    local res = if name == 'admin1' then '10m' else scaleFor(bbox);
    local clip = '.clip(%g, %g, %g, %g)' % [bbox.n, bbox.w, bbox.s, bbox.e];
    {
      type: 'scatter', mode: 'lines', name: name, uid: 'basemap-%s-%d' % [name, i],
      hoverinfo: 'skip', showlegend: false,
      x: '@NE.%s_%s%s.x' % [name, res, clip],
      y: '@NE.%s_%s%s.y' % [name, res, clip],
    } + $.axes(i) + basemapStyles[name] + std.get(style, name, {})
    for name in (
      if layers != null then layers
      else (
        if std.max(bbox.e - bbox.w, bbox.n - bbox.s) <= 20 then ['admin1'] else []
      ) + ['rivers', 'lakes', 'borders', 'disputed', 'coastline']
    )
  ],

  // A palette as a coloraxis: a stepped colorscale whose steps sit at the class
  // bounds, cmin / cmax at the outer bounds, and colorbar ticks at the bounds.
  // Under / over colors (when the palette packs them) get one extra class width
  // beyond each end. A palette with no bounds is a continuous colorscale.
  stepped(p):: (
    if !std.objectHas(p, 'bounds') then {
      local n = std.length(p.colors),
      colorscale: [[i / (n - 1), p.colors[i]] for i in std.range(0, n - 1)],
    } else {
      local b = p.bounds,
      local nb = std.length(b),
      local packed = std.length(p.colors) == nb + 1,
      local lo = if packed then b[0] - (b[1] - b[0]) else b[0],
      local hi = if packed then b[nb - 1] + (b[nb - 1] - b[nb - 2]) else b[nb - 1],
      local edges = (if packed then [lo] else []) + b + (if packed then [hi] else []),
      local pos(v) = (v - lo) / (hi - lo),
      // Ticks closer than 4% of the bar to the last one kept are dropped, so labels don't overlap.
      local ticks = std.foldl(
        function(kept, v) if kept == [] || pos(v) - pos(kept[std.length(kept) - 1]) >= 0.04 then kept + [v] else kept,
        b,
        []
      ),
      colorscale: std.flattenArrays([
        [[pos(edges[k]), p.colors[k]], [pos(edges[k + 1]), p.colors[k]]]
        for k in std.range(0, std.length(p.colors) - 1)
      ]),
      cmin: lo,
      cmax: hi,
      colorbar: { tickvals: ticks },
    }
  ),

  // Play / pause buttons and a slider for frames named by names, duration ms per frame.
  // A .gif output plays the frames at the same duration.
  player(names, duration=500):: {
    local step = { mode: 'immediate', frame: { duration: duration, redraw: true }, transition: { duration: 0 } },
    updatemenus: [{
      type: 'buttons', showactive: false, x: 0, y: 0, xanchor: 'right', yanchor: 'top', direction: 'left',
      buttons: [
        { label: 'Play', method: 'animate', args: [null, step { fromcurrent: true }] },
        { label: 'Pause', method: 'animate', args: [[null], step { frame+: { duration: 0 } }] },
      ],
    }],
    sliders: [{
      x: 0.05, len: 0.95, y: 0, yanchor: 'top', currentvalue: { prefix: '' },
      steps: [{ label: n, method: 'animate', args: [[n], step] } for n in names],
    }],
  },
}
