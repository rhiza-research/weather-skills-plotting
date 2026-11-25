---
name: report-dashboard
description: "Turn HTML you write into a safe, self-contained report (HTML and/or PDF) or a dashboard (HTML, with dropdowns, tabs and collapsible sections that switch between pre-made figures, and the plot skill's interactive Plotly figures in sandboxed frames). The HTML is cleaned to an allowlist, every <img> is embedded, and the weather_skills_history of each local image (figures from the plot skill) is attached. Use at the end of a pipeline to deliver findings with their figures and provenance."
license: MIT
compatibility: Requires Python 3.12 and uv; PDF output also needs the Pango system library (brew install pango, or apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0). Reads no credentials. Downloads https:// images the HTML links to; nothing else touches the network.
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/report_dashboard.py *)
metadata:
  version: "0.0.3"
  catalog-group: figure
---

# report-dashboard

Cleans HTML you write, embeds its images and the plot skill's interactive figures, and writes a self-contained report (`.html`, `.pdf`) or dashboard (`.html`) with the provenance of the figures it shows.

## Usage

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/report_dashboard.py -o OUT.html [-o OUT.pdf] --html "$(cat <<'EOF'
<title>…</title> …the page's HTML…
EOF
)"
```
- `--html` — the page's HTML text, not a file name. Quote the heredoc (`'EOF'`) so the shell leaves it alone.
- `-o` — `.html`, or `.pdf` for a report; repeat to write both.

A page is a **report** (`.html` and/or `.pdf`, same content) unless it has a `<select>`, `<input>`, `<details>` or interactive plot; then it is a **dashboard**: `.html` only, and `.pdf` exits 2.

### Allowed HTML
Anything else is removed, keeping its text (`<svg>` and `<math>` go with everything inside them): no scripts, event handlers, forms, `<canvas>`, `<iframe>` or `data:` URLs.
- Text: `h1`–`h6` `p` `br` `hr` `blockquote` `pre` `code` `kbd` `q` `cite` `strong` `b` `em` `i` `u` `s` `sub` `sup` `small` `mark` `abbr` `time`
- Layout: `div` `span` `section` `article` `header` `footer` `main` `aside` `figure` `figcaption`
- Lists, tables: `ul` `ol` `li` `dl` `dt` `dd` `table` `caption` `thead` `tbody` `tfoot` `tr` `th` `td` (`colspan`, `rowspan`) `colgroup` `col`
- `<a href>`: `http`, `https`, `mailto`, relative, `#id`. `<img src alt width height>`: see Images.
- Dashboard controls: `select` `option` (`value`, `selected`) `optgroup` `label` (`for`) `details` (`open`) `summary`, and `<input type="radio|checkbox" name value checked>`. Switch views with CSS `:checked` / `:has()`.
- On any tag: `id`, `class`, `title`, `style`.

### Styles
- `<style>` may hold rules, `@media` and `@page`, with any selector. Colours, borders, shadows, flex, grid, and linear and radial gradients are fine.
- These exit 2: `url()`, `@import`, `@font-face`, other at-rules, `conic-gradient()`, `clip-path`, `clip`, `mask`, `shape-outside`, `offset-path`, and shape functions such as `polygon()` and `path()`.
- Inline `style=""` keeps only text, colour, font, spacing, border, size, float and page-break properties; one with `url()`, `image-set()`, `@import` or a `\` escape exits 2.

### Images
- `<img src>` names a PNG, JPEG, GIF or SVG under the working directory, or an `https://` image; it is embedded in the page.
- `<img src="figs/x.html">` names interactive HTML the plot skill wrote; it shows live in a sandboxed frame (default full width × 500 px). Any other `.html` exits 2.
- Missing or outside files, fake images, and SVGs with scripts, external links or nested SVG images exit 2.

### Output
A self-contained page with a built-in stylesheet, carrying the history of its local images and plots and the `--html` text.

### Example
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/report_dashboard.py -o outlook.html --html "$(cat <<'EOF'
<title>Kenya outlook</title>
<style>.v{display:none} body:has(#w option[value="1"]:checked) .w1, body:has(#w option[value="2"]:checked) .w2{display:block}</style>
<label for="w">Week</label> <select id="w"><option value="1" selected>1</option><option value="2">2</option></select>
<figure class="v w1"><img src="figs/w1.html" alt="Week 1"></figure>
<figure class="v w2"><img src="figs/w2.png" alt="Week 2"></figure>
EOF
)"
```

## Details

Reference for people maintaining or reviewing the skill; the agent reads only Usage.

Two rules hold for every page:
- The HTML you pass cannot draw figures: `<svg>`, `<canvas>`, MathML, `<object>`, `<embed>`, media, `data:` images, CSS that loads pictures, and CSS that draws pies or shapes (see Styles) are all removed or refused. Figures come only from files (see Images), made by other skills.
- Nothing runs scripts except the plot skill's interactive `.html`: scripts and event handlers you write are removed, an SVG with a script is refused, and any other `.html` is refused.

### What the HTML may contain

Anything not listed is removed. A removed tag keeps its text (`<button>Go</button>` leaves `Go`), except `<head>`, `<title>`, `<script>`, `<style>`, `<template>`, `<noscript>`, `<iframe>`, `<object>`, `<svg>` and `<math>`, which go with everything inside them.

| Group | Tags | Attributes kept | Report | Dashboard | PDF |
|---|---|---|---|---|---|
| Text | `h1`–`h6`, `p`, `br`, `hr`, `blockquote`, `pre`, `code`, `kbd`, `q`, `cite`, `strong`, `b`, `em`, `i`, `u`, `s`, `sub`, `sup`, `small`, `mark`, `abbr`, `time` | `datetime` on `time` | yes | yes | yes |
| Layout | `div`, `span`, `section`, `article`, `header`, `footer`, `main`, `aside`, `figure`, `figcaption` | — | yes | yes | yes |
| Lists | `ul`, `ol`, `li`, `dl`, `dt`, `dd` | `start`, `type` on `ol` | yes | yes | yes |
| Tables | `table`, `caption`, `thead`, `tbody`, `tfoot`, `tr`, `th`, `td`, `colgroup`, `col` | `colspan`, `rowspan`, `scope`, `span` | yes | yes | yes |
| Links | `a` | `href`: `http`, `https`, `mailto`, relative or `#anchor`; given `rel="noopener noreferrer"` | yes | yes | yes |
| Images | `img` naming a PNG, JPEG, GIF or SVG | `src` (see Images), `alt`, `width`, `height` | yes | yes | yes |
| Interactive plots | `img` naming the plot skill's `.html` | `src`, `alt` (the frame's title), `width`, `height` (pixels) | — | yes | refused |
| Style | `<style>` blocks | — (see Styles) | yes | yes | yes |
| Controls | `select`, `option`, `optgroup`, `input`, `label`, `details`, `summary` | `value`, `selected` on `option`; `label` on `optgroup`; `type`, `name`, `value`, `checked` on `input`; `for` on `label`; `open` on `details` | — | yes | refused |

- On every tag: `id`, `class`, `title`, `lang`, `dir`, `style`. Event handlers (`onclick`, …) and every other attribute are removed.
- `<input>` must be `type="radio"` or `type="checkbox"`; any other type, or none, exits 2. There are no forms: `<form>`, `<button>` and `<textarea>` are removed, so nothing is ever submitted.
- A page with any `<select>`, `<input>`, `<details>` or interactive plot is a dashboard: asking for `.pdf` exits 2 before anything is written. For a printable report, leave the controls out (show each view in turn) and use the plot skill's `.png` or `.svg` of the figure.

### Styles
- `<style>` blocks may hold style rules, `@media` and `@page`. Selectors are free, including `:checked` and `:has()`, which is how controls switch views.
- Anything that loads a resource exits 2: `url()`, `image-set()` and other image functions, `@import`, `@font-face`, and any other at-rule. Show pictures with `<img>`, never CSS.
- Colours, borders, rounded corners, shadows, flex and grid layout, and `linear-gradient()`/`radial-gradient()` (for bands and shading) are fine. CSS that draws a chart in a line exits 2: `conic-gradient()` (a pie), shape functions (`polygon()`, `path()`, `circle()`, `ellipse()`, `inset()`, `rect()`), and `clip-path`, `clip`, `mask`, `shape-outside` and `offset-path`.
- Inline `style=""` keeps text, colour, font, spacing, border, size, float and page-break properties only; others (`background`, `position`, `display`, …) are removed silently. Put anything else in a `<style>` block. An inline style holding `url()`, an image function, `@import` or a backslash escape exits 2.
- Only `<style>` elements of the page itself count; one inside a comment, `<textarea>`, `<noscript>` or `<svg>` is ignored.
- `@page` takes declarations only; margin boxes such as `@top-center` exit 2.
- `<style>` ends at its first `</style>`, as in a browser, so do not write `</style>` inside a CSS string.

### Images
- A local PNG, JPEG, GIF or SVG under the working directory, or an `https://` URL (downloaded once, at most 10 MB, and embedded; it has no provenance). The bytes must be a real image of that type.
- An SVG is refused if it has an external `href`, a nested SVG image (`data:image/svg+xml`), a `url()` other than `#id`, `image-set()`, `@import`, an `<!ENTITY>`, a `<!DOCTYPE>` other than SVG 1.1's, a `<script>` (with or without a namespace prefix), `<foreignObject>`, `<iframe>`, `<embed>`, `<object>` or `<handler>`, an event handler, or an animation of an `href`. Character references and CSS escapes are decoded before checking.
- Any image that is refused exits 2 naming it; `http://`, `file:`, `data:` and other URL schemes are refused too.

### Interactive plots
- Write `<img src="figs/rain.html" alt="…">` naming an `.html` the plot skill wrote; it becomes a frame showing the live Plotly figure (hover, zoom, pan, play). Size it with `width`/`height` in pixels; the default is the full width and 500 px high.
- Only an `.html` whose history ends in a `plot` step is taken, and only its figure (data, layout and frames, read as JSON) is kept: the frame's page is written again by plotly with the plotly.js this skill installs, so no script from the file runs. Any other `.html`, or one with no Plotly figure, exits 2. You never write `<script>` or `<iframe>` yourself.
- The frame is sandboxed (scripts, but no access to the page, its storage or top-level navigation), and the page's Content-Security-Policy lets only the rebuilt page's exact scripts run and blocks all network access, inside the frame too.
- The plot's history is recorded as an input, like an image's.
- Each plot carries its own copy of plotly.js, about 5 MB. A plot that starts hidden behind a control takes a few seconds to draw the first time it is shown.

### Notes
- Only local image files are recorded as inputs in the provenance; downloaded `https://` images are not. Make figures with the `plot` skill and reference the files it wrote, so the page carries their history.
- The provenance skill's reproduction script cannot replay this step yet: the image paths sit inside the `--html` text, so it cannot point them at the figures it rebuilds.
- Dashboards rely on CSS `:has()` (Chrome and Edge 105+, Safari 15.4+, Firefox 121+). Every view is drawn in advance; nothing is computed in the browser.
- The PDF is rendered by WeasyPrint, which needs the Pango library on the system; without it `.pdf` output exits 1 naming the install command; `.html` outputs of the same run are written first, so they are still there. Images wider than the page are shrunk to fit; set `width` on an `<img>` to size it.
- The HTML output sets a Content-Security-Policy that lets the page load nothing but its own embedded images and styles, and run nothing but the scripts of embedded plots.
- A report's `.html` and `.pdf` come from the same cleaned page. The medium still differs: on screen the text column is at most 900 px wide; the PDF is paged on A4 and carries the provenance mark on its first page when every image's history is complete.
- Provenance: a join of the histories of the local images, in the order they first appear (each image once), with the `--html` text recorded in `args`. Read it with the provenance skill. The PDF gets the provenance mark only when every local image has a complete history.
