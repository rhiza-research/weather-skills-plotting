// Helpers for plot specs. Every function returns plain Plotly JSON (or @ reference
// strings inside it); override any key with +, e.g. ws.map(bbox) + {height: 600}.
//
// bbox is {n, w, s, e} in degrees, as inputs.NAME.bbox gives it.
local palettes = import 'palettes.libsonnet';

local round(x) = std.floor(x + 0.5);

// Margins (px) around the plotting area: room for the title, ticks and a colorbar.
local margin = { l: 50, r: 150, t: 70, b: 70 };

// The legend sits in a row under the maps, clear of the colorbar on the right.
local legend = { orientation: 'h', x: 0, y: -0.06, yanchor: 'top' };

local months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

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

  // The house Plotly template: colorway (no grey, kept for ensemble members) and box outlines.
  template: {
    layout: {
      colorway: ['#4c72b0', '#dd8452', '#55a868', '#c44e52', '#8172b3', '#937860', '#da8bc3', '#17becf', '#ccb974', '#64b5cd'],
      shapedefaults: { fillcolor: 'rgba(0,0,0,0)', opacity: 1, line: { width: 2, color: '#333333' } },
    },
  },

  // bbox widened on every side by frac of its larger span. A bbox from inputs.NAME.bbox
  // runs between the outermost cell centres, so without a pad the edge cells are cut
  // in half; ws.map, ws.grid and ws.basemap pad by 3% unless given pad=0.
  // A box with w > e crosses the dateline; its east edge is taken past 180° (170 to 200).
  pad(bbox, frac=0.03):: {
    local east = if bbox.w > bbox.e then bbox.e + 360 else bbox.e,
    local d = frac * std.max(east - bbox.w, bbox.n - bbox.s),
    n: bbox.n + d, s: bbox.s - d, w: bbox.w - d, e: east + d,
  },

  // Panel i's axis names (0 → x / y, 1 → x2 / y2, …), to add to a trace.
  axes(i):: {
    xaxis: if i == 0 then 'x' else 'x%d' % (i + 1),
    yaxis: if i == 0 then 'y' else 'y%d' % (i + 1),
  },

  // One map: lon/lat axes on the bbox with equal degrees, and a canvas sized to its aspect.
  map(box, width=760, pad=0.03)::
    local bbox = $.pad(box, pad);
    {
    local plotw = width - margin.l - margin.r,
    width: width,
    height: round(plotw * (bbox.n - bbox.s) / (bbox.e - bbox.w)) + margin.t + margin.b,
    margin: margin,
    legend: legend,
    xaxis: { range: [bbox.w, bbox.e], showgrid: false, zeroline: false, ticksuffix: '°', constrain: 'domain' },
    yaxis: {
      range: [bbox.s, bbox.n], showgrid: false, zeroline: false, ticksuffix: '°',
      scaleanchor: 'x', scaleratio: 1, constrain: 'domain',
    },
  },

  // Maps in a grid, filled row by row from the top left: panel i is ws.axes(i).
  // Tick labels show on the bottom row (longitude) and left column (latitude).
  grid(box, rows, cols, panel=340, gap=0.04, pad=0.03, empty=[])::
    local bbox = $.pad(box, pad);
    local filled(i) = !std.member(empty, i);
    // Longitude labels on the lowest filled panel of each column, latitude labels on
    // the leftmost filled panel of each row; empty panels are hidden.
    local lowest(i) = filled(i) && [j for j in std.range(i + cols, rows * cols - 1) if (j - i) % cols == 0 && filled(j)] == [];
    local leftmost(i) = filled(i) && [j for j in std.range(i - i % cols, i) if j < i && filled(j)] == [];
    {
    local aspect = (bbox.n - bbox.s) / (bbox.e - bbox.w),
    width: cols * panel + margin.l + margin.r,
    height: round(rows * panel * aspect / (1 - gap)) + margin.t + margin.b,
    margin: margin,
    legend: legend,
  } + {
    [if i == 0 then 'xaxis' else 'xaxis%d' % (i + 1)]: {
      local c = i % cols,
      local r = std.floor(i / cols),
      domain: [c / cols + gap / 2, (c + 1) / cols - gap / 2],
      range: [bbox.w, bbox.e], showgrid: false, zeroline: false, ticksuffix: '°',
      constrain: 'domain', showticklabels: lowest(i), visible: filled(i),
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
      constrain: 'domain', showticklabels: leftmost(i), visible: filled(i),
      anchor: if i == 0 then 'x' else 'x%d' % (i + 1),
    }
    for i in std.range(0, rows * cols - 1)
  },

  // A row label left of panel i (the first panel of a row), turned on its side.
  rowTitle(i, text):: {
    text: text, showarrow: false, font: { size: 13 }, textangle: -90,
    xref: (if i == 0 then 'x' else 'x%d' % (i + 1)) + ' domain', x: 0, xshift: -48, xanchor: 'center',
    yref: (if i == 0 then 'y' else 'y%d' % (i + 1)) + ' domain', y: 0.5, yanchor: 'middle',
  },

  // A title above panel i, as a layout annotation.
  panelTitle(i, text):: {
    text: text, showarrow: false, font: { size: 13 },
    xref: (if i == 0 then 'x' else 'x%d' % (i + 1)) + ' domain', x: 0.5, xanchor: 'center',
    yref: (if i == 0 then 'y' else 'y%d' % (i + 1)) + ' domain', y: 1.01, yanchor: 'bottom',
  },

  // Base-map lines from the built-in Natural Earth input NE on panel i, clipped to
  // the padded bbox. Every layer is on unless switched off by name; admin1='auto'
  // draws admin-1 lines on maps up to 20° across. Drawn bottom first: admin1, rivers,
  // lakes (filled, opaque over the data), borders, disputed, coastline.
  // style overrides a layer's Plotly keys: style={borders: {line: {color: 'red'}}}.
  basemap(box, i=0, coastline=true, borders=true, disputed=true, lakes=true, rivers=true,
          admin1='auto', style={}, pad=0.03)::
    local bbox = $.pad(box, pad);
    local on = {
      admin1: if admin1 == 'auto' then std.max(box.e - box.w, box.n - box.s) <= 20 else admin1,
      rivers: rivers, lakes: lakes, borders: borders, disputed: disputed, coastline: coastline,
    };
    [
      local res = if name == 'admin1' then '10m' else scaleFor(bbox);
      local clip = '.clip(%g, %g, %g, %g)' % [bbox.n, bbox.w, bbox.s, bbox.e];
      {
        type: 'scatter', mode: 'lines', name: name, uid: 'basemap-%s-%d' % [name, i],
        hoverinfo: 'skip', showlegend: false,
        x: '@NE.%s_%s%s.x' % [name, res, clip],
        y: '@NE.%s_%s%s.y' % [name, res, clip],
      } + $.axes(i) + basemapStyles[name] + std.get(style, name, {})
      for name in ['admin1', 'rivers', 'lakes', 'borders', 'disputed', 'coastline']
      if on[name]
    ],

  // A palette as a coloraxis: a stepped colorscale whose steps sit at the class
  // bounds, cmin / cmax at the outer bounds, and colorbar ticks at the bounds.
  // Under / over colors (when the palette packs them) get one extra class width
  // beyond each end. A palette with no bounds is a continuous colorscale.
  // An ISO date or time from std.extVar('inputs') as text: '2026-10-26' → '26 Oct 2026',
  // '2026-10-30T12:00:00' → '30 Oct 2026 12 UTC'. year=false leaves the year out.
  date(t, year=true)::
    local day = std.parseInt(std.substr(t, 8, 2));
    local text = '%d %s' % [day, months[std.parseInt(std.substr(t, 5, 2)) - 1]]
                 + (if year then ' ' + std.substr(t, 0, 4) else '');
    if std.length(t) > 10 && std.substr(t, 11, 8) != '00:00:00' then text + ' ' + std.substr(t, 11, 2) + ' UTC' else text,

  // xaxis ticks for a day-of-year axis (.dt.dayofyear): the 1st of each month.
  // Days are counted in a non-leap year, so after 28 Feb a leap year sits a day later.
  dayOfYearTicks:: {
    local starts = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335],
    tickvals: starts,
    ticktext: ['1 ' + m for m in months],
  },

  stepped(p):: (
    if !std.objectHas(p, 'bounds') then {
      local n = std.length(p.colors),
      colorscale: [[i / (n - 1), p.colors[i]] for i in std.range(0, n - 1)],
    } else {
      local b = p.bounds,
      local nb = std.length(b),
      local packed = std.length(p.colors) == nb + 1,
      assert std.length(p.colors) == nb - 1 || packed :
             'palette has %d colors for %d bounds: give one color per class (%d), or under + classes + over (%d)'
             % [std.length(p.colors), nb, nb - 1, nb + 1],
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

  // A class palette on a coloraxis, with a colorbar of equal-height bands, one per
  // class, labelled at the bounds (or by the palette's labels, one per class);
  // under / over colors are triangles at the ends.
  // The map colors come from ws.stepped (exact at the bounds); Plotly's own colorbar
  // is hidden and this one is drawn as layout shapes and annotations, so it adds to
  // the layout's shapes and annotations (write yours as annotations+: [...] after it).
  // x, y, len and width are fractions of the plotting area (paper), from its bottom left.
  classBar(p, title='', axis='coloraxis', x=1.03, y=0.05, len=0.85, width=0.03, format='%g'):: {
    local b = p.bounds,
    local nb = std.length(b),
    local packed = std.length(p.colors) == nb + 1,
    local classes = if packed then p.colors[1:nb] else p.colors,
    local h = len / (nb - 1),
    local box(y0, y1, color) = {
      type: 'rect', xref: 'paper', yref: 'paper', x0: x, x1: x + width, y0: y0, y1: y1,
      fillcolor: color, line: { width: 0.5, color: '#333333' }, layer: 'above',
    },
    local triangle(base, tip, color) = {
      type: 'path', xref: 'paper', yref: 'paper', fillcolor: color, layer: 'above',
      line: { width: 0.5, color: '#333333' },
      path: 'M %f,%f L %f,%f L %f,%f Z' % [x, base, x + width, base, x + width / 2, tip],
    },
    [axis]: $.stepped(p) + { showscale: false },
    shapes+: [box(y + k * h, y + (k + 1) * h, classes[k]) for k in std.range(0, nb - 2)]
             + (if packed then [
                  triangle(y, y - 0.8 * h, p.colors[0]),
                  triangle(y + len, y + len + 0.8 * h, p.colors[nb]),
                ] else []),
    local label(text, at) = {
      text: text, showarrow: false, font: { size: 11 },
      xref: 'paper', yref: 'paper', x: x + width + 0.005, y: at, xanchor: 'left', yanchor: 'middle',
    },
    // A palette with labels names each class at its middle; otherwise the bounds are labelled.
    annotations+: (
      if std.objectHas(p, 'labels') then [label(p.labels[k], y + (k + 0.5) * h) for k in std.range(0, nb - 2)]
      else [label(format % b[i], y + i * h) for i in std.range(0, nb - 1)]
    ) + (if title == '' then [] else [{
      text: title, showarrow: false, font: { size: 12 },
      xref: 'paper', yref: 'paper', x: x + width / 2, y: y + len + (if packed then 0.8 * h else 0) + 0.015,
      xanchor: 'center', yanchor: 'bottom',
    }]),
  },

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
