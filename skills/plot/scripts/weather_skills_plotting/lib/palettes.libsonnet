// Color tables. A class palette is {colors, bounds}: colors holds one color per
// class (between two bounds), or under + classes + over. A palette with no bounds
// is a list of colors for a continuous scale. ws.stepped turns one into a coloraxis.
//
// ppt_daily … ppt_season are rainfall totals in mm (0–50, 0–200, 0–400, 0–1000);
// ppt_anom_* are anomalies in mm (±50, ±200, ±300, ±500); ppt_total runs to 2500 mm.
// ppt_poa is percent of normal; spi the standardized precipitation index; hits,
// bias and mae color verify maps.
{
  ppt_daily: {
    colors: ['#ffffff', '#ffffff', '#f6e8c3', '#e8d4a0', '#c8ffbe', '#78f573', '#1eb41e', '#50a5f5', '#1e6eeb', '#a08cff', '#7060dc'],
    bounds: [0, 1, 2, 5, 10, 15, 20, 30, 40, 50],
  },
  ppt_week: {
    colors: ['#ffffff', '#ffffff', '#f6e8c3', '#e8d4a0', '#c8ffbe', '#78f573', '#1eb41e', '#50a5f5', '#1e6eeb', '#a08cff', '#7060dc', '#fffaaa', '#ffa000', '#ff1400', '#a50000'],
    bounds: [0, 1, 2, 5, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200],
  },
  ppt_month: {
    colors: ['#ffffff', '#ffffff', '#f6e8c3', '#e8d4a0', '#c8ffbe', '#78f573', '#1eb41e', '#50a5f5', '#1e6eeb', '#a08cff', '#7060dc', '#fffaaa', '#ffa000', '#ff1400', '#a50000', '#e68c8c'],
    bounds: [0, 1, 2, 5, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200, 400],
  },
  ppt_season: {
    colors: ['#ffffff', '#ffffff', '#f6e8c3', '#e8d4a0', '#c8ffbe', '#78f573', '#1eb41e', '#50a5f5', '#1e6eeb', '#a08cff', '#7060dc', '#fffaaa', '#ffa000', '#ff1400', '#a50000', '#e68c8c', '#7a0000', '#5a0000'],
    bounds: [0, 1, 2, 5, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200, 400, 700, 1000],
  },
  ppt_total: {
    colors: ['#ffffff', '#ffffff', '#c8ffbe', '#78f573', '#1eb41e', '#b4f0fa', '#50a5f5', '#1e6eeb', '#dcdcff', '#a08cff', '#7060dc', '#fffaaa', '#ffa000', '#ff1400', '#a50000', '#e68c8c', '#ffe6e6'],
    bounds: [0, 2, 5, 10, 25, 50, 75, 100, 150, 200, 300, 500, 750, 1000, 1500, 2500],
  },
  ppt_anom_daily: {
    colors: ['#785046', '#b48c82', '#f0dcd2', '#ffffff', '#c8ffbe', '#78f573', '#1eb41e'],
    bounds: [-50, -25, -10, 10, 25, 50],
  },
  ppt_anom_week: {
    colors: ['#ffa000', '#ffe878', '#785046', '#b48c82', '#f0dcd2', '#ffffff', '#c8ffbe', '#78f573', '#1eb41e', '#96d2fa', '#2882f0'],
    bounds: [-200, -100, -50, -25, -10, 10, 25, 50, 100, 200],
  },
  ppt_anom_month: {
    colors: ['#ff3200', '#ffa000', '#ffe878', '#785046', '#b48c82', '#f0dcd2', '#ffffff', '#c8ffbe', '#78f573', '#1eb41e', '#96d2fa', '#2882f0', '#dcdcff'],
    bounds: [-300, -200, -100, -50, -25, -10, 10, 25, 50, 100, 200, 300],
  },
  ppt_anom_season: {
    colors: ['#c00000', '#ff3200', '#ffa000', '#ffe878', '#785046', '#b48c82', '#f0dcd2', '#ffffff', '#c8ffbe', '#78f573', '#1eb41e', '#96d2fa', '#2882f0', '#dcdcff', '#8070eb'],
    bounds: [-500, -300, -200, -100, -50, -25, -10, 10, 25, 50, 100, 200, 300, 500],
  },
  ppt_master: {
    colors: ['#ffffff', '#ffffff', '#f6e8c3', '#e8d4a0', '#c8ffbe', '#78f573', '#1eb41e', '#50a5f5', '#1e6eeb', '#a08cff', '#7060dc', '#fffaaa', '#ffa000', '#ff1400', '#a50000', '#e68c8c', '#7a0000', '#5a0000'],
    bounds: [0, 1, 2, 5, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200, 400, 700, 1000],
  },
  ppt_anom_master: {
    colors: ['#c00000', '#ff3200', '#ffa000', '#ffe878', '#785046', '#b48c82', '#f0dcd2', '#ffffff', '#c8ffbe', '#78f573', '#1eb41e', '#96d2fa', '#2882f0', '#dcdcff', '#8070eb'],
    bounds: [-500, -300, -200, -100, -50, -25, -10, 10, 25, 50, 100, 200, 300, 500],
  },
  ppt_poa: {
    colors: ['#e1beb4', '#c00000', '#ff3200', '#ffa000', '#ffe878', '#ffffff', '#c8ffbe', '#78f573', '#1eb41e', '#96d2fa', '#2882f0'],
    bounds: [30, 45, 60, 75, 90, 110, 125, 150, 200, 300],
  },
  ppt_spp: {
    colors: ['#dcdcdc', '#ffffff', '#ffe878', '#ffa000', '#ff3200', '#c00000', '#c8ffbe', '#96f58c', '#37d23c', '#0fa00f', '#b4f0fa', '#78b9fa', '#2882f0', '#1464d2'],
    bounds: [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5],
  },
  spi: {
    colors: ['#730000', '#e70000', '#ffaa00', '#ffd37b', '#ffff00', '#ffffff', '#bdebff', '#73b2ff', '#0071ff', '#004dad', '#ad00e7'],
    bounds: [-2.5, -2, -1.5, -1.2, -0.7, -0.5, 0.5, 0.7, 1.2, 1.5, 2, 2.5],
  },
  hits: {
    colors: ['#d73027', '#ffffff', '#1a9850'],
    bounds: [-1.5, -0.5, 0.5, 1.5],
  },
  bias: {
    colors: ['#053061', '#2166ac', '#4393c3', '#92c5de', '#d1e5f0', '#ffffff', '#fddbc7', '#f4a582', '#d6604d', '#b2182b', '#67001f'],
  },
  precip_bias: {
    colors: ['#543005', '#8c510a', '#bf812d', '#dfc27d', '#f6e8c3', '#f5f5f5', '#c7eae5', '#80cdc1', '#35978f', '#01665e', '#003c30'],
  },
  mae: {
    colors: ['#ffffff', '#fddbc7', '#f4a582', '#d6604d', '#b2182b', '#67001f'],
  },
  wind_rose: {
    colors: ['#c7e9b4', '#7fcdbb', '#41b6c4', '#1d91c0', '#225ea8', '#253494', '#081d58'],
  },
  colorblind: {
    colors: ['#0173b2', '#de8f05', '#029e73', '#d55e00', '#cc78bc', '#ca9161', '#fbafe4', '#949494', '#ece133', '#56b4e9'],
  },
  rocket: {
    colors: ['#f7ccaf', '#f6ab83', '#f58860', '#f06043', '#e43841', '#cb1b4f', '#a8185a', '#841e5a', '#611f53', '#3f1b43', '#20122e'],
  },
}
