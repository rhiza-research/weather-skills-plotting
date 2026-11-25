# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "weather-skills-core>=0.4.0",
#   "nh3>=0.2.18",
#   "pillow",
#   "plotly>=7.1",
#   "tinycss2>=1.4",
#   "weasyprint>=70",
# ]
# ///
"""Sanitize a report or dashboard in HTML, embed its images, and write self-contained HTML or PDF."""

import argparse
import base64
import hashlib
import io
import json
import re
import sys
import urllib.request
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path

import nh3
import tinycss2
from weather_skills_core import DataError, UsageError, provenance, weather_skill
from weather_skills_core.decorator import build_history

# Auto-populated by the version-bump CI workflow. Do not edit manually.
_SKILL_VERSION = "0.0.3"

# Everything a report needs and nothing that runs code or loads resources.
REPORT_TAGS = {
    *("h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "div", "span"),
    *("section", "article", "header", "footer", "main", "aside", "figure", "figcaption"),
    *("ul", "ol", "li", "dl", "dt", "dd", "blockquote", "pre", "code", "kbd", "q", "cite"),
    *("strong", "b", "em", "i", "u", "s", "sub", "sup", "small", "mark", "abbr", "time"),
    *("table", "caption", "thead", "tbody", "tfoot", "tr", "th", "td", "colgroup", "col"),
    *("a", "img"),
}
# Controls a dashboard switches views with, through CSS (:checked, :has()); never a form.
DASHBOARD_TAGS = {"select", "option", "optgroup", "input", "label", "details", "summary"}
# Any of these makes the page a dashboard, which a PDF cannot show.
INTERACTIVE = ("select", "input", "details")
INPUT_TYPES = {"radio", "checkbox"}
TAGS = REPORT_TAGS | DASHBOARD_TAGS
ATTRIBUTES = {
    "*": {"id", "class", "title", "lang", "dir", "style"},
    "a": {"href"},
    "img": {"src", "alt", "width", "height"},
    "th": {"colspan", "rowspan", "scope"},
    "td": {"colspan", "rowspan"},
    "col": {"span"},
    "colgroup": {"span"},
    "ol": {"start", "type"},
    "time": {"datetime"},
    "option": {"value", "selected"},
    "optgroup": {"label"},
    "input": {"type", "name", "value", "checked"},
    "label": {"for"},
    "details": {"open"},
}
# Dropped along with everything inside them, not just unwrapped.
DROP_WITH_CONTENT = {"head", "title", "script", "style", "template", "noscript", "iframe", "object"}
# Inline style properties kept; a style value that could load something is refused (_STYLE_LOADS).
STYLE_PROPERTIES = {
    *("color", "background-color", "font-family", "font-size", "font-style", "font-weight"),
    *("line-height", "text-align", "text-decoration", "text-indent", "text-transform"),
    *("vertical-align", "white-space", "width", "height", "max-width", "min-width"),
    *("margin", "margin-top", "margin-right", "margin-bottom", "margin-left"),
    *("padding", "padding-top", "padding-right", "padding-bottom", "padding-left"),
    *("border", "border-top", "border-right", "border-bottom", "border-left"),
    *("border-color", "border-style", "border-width", "border-collapse", "border-spacing"),
    *("float", "clear", "page-break-before", "page-break-after", "page-break-inside"),
}
# CSS functions that fetch a resource; with url() tokens, refused in <style> blocks.
CSS_LOADERS = {"url", "image", "image-set", "-webkit-image-set", "cross-fade", "element", "src"}
# CSS that draws a chart in a line: a pie (conic gradients) or any shape from coordinates.
# Linear and radial gradients stay, for bands and shading.
CSS_SHAPES = {"conic-gradient", "repeating-conic-gradient", "polygon", "path", "circle"}
CSS_SHAPES |= {"ellipse", "inset", "rect", "xywh", "shape"}
SHAPE_PROPERTIES = ("clip-path", "-webkit-clip-path", "mask", "-webkit-mask", "shape-", "offset")
LINK_SCHEMES = {"http", "https", "mailto"}
MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif"}
MAX_REMOTE_BYTES = 10_000_000
# An inline style value that could load something: url(), an image function, @import, or a
# backslash escape (which can spell any of them).
_STYLE_LOADS = re.compile(
    r"url\(|image(?:-set)?\(|cross-fade\(|element\(|@import|\\", re.IGNORECASE
)
# An SVG reaching outside itself or running code, matched after character references and CSS
# escapes are decoded: an external href or a nested SVG image, a url() other than #id, a CSS
# image function or @import, an entity, a DOCTYPE other than SVG 1.1's, a script, a foreign
# or embedding element, an event handler, or an animation of an href.
_SVG_UNSAFE = re.compile(
    r"""href\s*=\s*(?!["']?(?:#|data:image/(?!svg)))|url\(\s*["']?(?!#)|image(?:-set)?\("""
    r"""|@import|<!ENTITY|<!DOCTYPE(?!\s+svg\s*>|\s+svg\s+PUBLIC\s+"-//W3C//DTD SVG 1\.1//EN"\s+"""
    r""""http://www\.w3\.org/Graphics/SVG/1\.1/DTD/svg11\.dtd"\s*>)"""
    r"""|<(?:[\w.-]+:)?(?:script|foreignObject|handler|iframe|embed|object)\b"""
    r"""|[\s/"']on\w+\s*=|attributeName\s*=\s*["']?(?:[\w.-]+:)?href""",
    re.IGNORECASE,
)
_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)
_STYLE = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.IGNORECASE | re.DOTALL)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

CSS = """
@page { size: a4; margin: 2cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10.5pt; line-height: 1.45;
       color: #1f2328; }
@media screen { body { max-width: 900px; margin: 0 auto; padding: 24px 16px; } }
h1, h2, h3, h4 { color: #0b3d5c; line-height: 1.2; margin: 1.2em 0 0.4em; }
h1 { font-size: 22pt; border-bottom: 2px solid #0b3d5c; padding-bottom: 4px; }
h2 { font-size: 15pt; border-bottom: 1px solid #d0d7de; padding-bottom: 2px; }
h3 { font-size: 12.5pt; }
p, ul, ol, dl, table, figure, blockquote, pre { margin: 0 0 0.8em; }
a { color: #0969da; }
img { max-width: 100%; height: auto; }
figure { margin: 1em 0; text-align: center; }
figcaption { font-size: 9pt; color: #57606a; margin-top: 4px; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; }
th, td { border: 1px solid #d0d7de; padding: 4px 8px; text-align: left; vertical-align: top; }
th { background-color: #f3f5f7; font-weight: bold; }
caption { font-weight: bold; padding: 4px 0; text-align: left; }
blockquote { border-left: 3px solid #d0d7de; color: #57606a; padding-left: 12px; }
pre, code { font-family: Courier, monospace; font-size: 9pt; background-color: #f6f8fa; }
pre { padding: 8px; white-space: pre-wrap; }
"""
# A second guard in browsers: the page may load nothing but its own data: images and styles.
CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'"


def _image_data(src: str, base: Path, root: Path) -> tuple[str, Path | None]:
    """``(data URI, local path or None)`` for one ``<img src>``; raises UsageError if refused."""
    if src.lower().startswith("https://"):
        try:
            with urllib.request.urlopen(src, timeout=30) as resp:
                data = resp.read(MAX_REMOTE_BYTES + 1)
        except Exception as exc:  # noqa: BLE001
            raise UsageError(f"could not download image {src}: {exc}") from None
        if len(data) > MAX_REMOTE_BYTES:
            raise UsageError(f"image {src} is over {MAX_REMOTE_BYTES // 1_000_000} MB")
        path = None
    else:
        path = _local(src, base, root)
        data = path.read_bytes()
    return f"data:{_mime(data, src)};base64,{base64.b64encode(data).decode()}", path


def _local(src: str, base: Path, root: Path) -> Path:
    """The existing file under ``root`` that a local ``src`` names; raises UsageError if not."""
    if re.match(r"^[a-z][a-z0-9+.-]*:|^//", src, re.IGNORECASE):
        raise UsageError(f"image {src!r}: only local files and https:// URLs can be embedded")
    path = (base / src).resolve()
    if not path.is_relative_to(root):
        raise UsageError(f"image {src!r} is outside the working directory {root}")
    if not path.is_file():
        raise UsageError(f"image {src!r} not found (looked for {path})")
    return path


def _plot_page(path: Path, src: str) -> tuple[str, list[str]]:
    """A new page of the plot skill's interactive figure and the CSP hashes of its scripts.

    Only the figure's data, layout and frames are read from the file, as JSON; plotly writes
    the page again with its own plotly.js, so no script from the file ever runs.
    """
    history = provenance.load_figure_history(path) or []
    if not history or not isinstance(history[-1], dict) or history[-1].get("skill") != "plot":
        raise UsageError(
            f"{src!r}: only interactive HTML written by the plot skill can be embedded"
        )
    text = path.read_text(encoding="utf-8")
    # The figure script plotly writes: Plotly.newPlot("id", data, layout, config), then
    # Plotly.addFrames('id', frames) for an animation.
    decode = json.JSONDecoder().raw_decode
    comma = re.compile(r"\s*,\s*")
    try:
        data, end = decode(text, re.search(r'Plotly\.newPlot\(\s*"[\w-]+",\s*', text).end())
        layout, end = decode(text, comma.match(text, end).end())
        _config, end = decode(text, comma.match(text, end).end())
        m = re.compile(r"\s*\)\.then\(function\(\)\{\s*Plotly\.addFrames\('[\w-]+',\s*").match(
            text, end
        )
        frames = decode(text, m.end())[0] if m else []
    except (AttributeError, ValueError):
        data = None
    if not (isinstance(data, list) and isinstance(layout, dict) and isinstance(frames, list)):
        raise UsageError(f"{src!r}: no Plotly figure found; embed an .html the plot skill wrote")
    import plotly.io as pio

    page = pio.to_html(
        {"data": data, "layout": layout, "frames": frames},
        config={"responsive": True, "scrollZoom": True, "displaylogo": False},
        include_plotlyjs=True,
        full_html=True,
        auto_play=False,
        validate=False,
        div_id="plot",
    )
    # The HTML parser turns CR LF into LF; hash the scripts as the browser will see them.
    page = page.replace("\r\n", "\n").replace("\r", "\n")
    hashes = []
    for m in _SCRIPT.finditer(page):
        digest = base64.b64encode(hashlib.sha256(m.group(2).encode()).digest()).decode()
        hashes.append(f"'sha256-{digest}'")
    return page, hashes


def _iframe(img: str, text: str) -> str:
    """A sandboxed frame holding a plot page, sized from the ``<img>`` it replaces."""
    attrs = dict(re.findall(r'\b(alt|width|height)="([^"]*)"', img))
    width = f"{attrs['width']}px" if attrs.get("width", "").isdigit() else "100%"
    height = f"{attrs['height']}px" if attrs.get("height", "").isdigit() else "500px"
    # allow-scripts without allow-same-origin: the plot runs in an opaque origin, so it cannot
    # reach this page or its storage, and the CSP it inherits keeps it off the network.
    return (
        '<iframe class="plotly" sandbox="allow-scripts allow-downloads" '
        f'title="{attrs.get("alt") or "Interactive figure"}" '
        f'style="width: {width}; height: {height}; border: 0" '
        f'srcdoc="{escape(text, quote=True)}"></iframe>'
    )


def _mime(data: bytes, src: str) -> str:
    """The MIME type of real image bytes; anything else is refused."""
    head = data[:512].lstrip().lower()
    if head.startswith((b"<?xml", b"<svg", b"<!doctype svg")) and b"<svg" in data[:4096].lower():
        # Decode character references, then CSS escapes, so neither can hide a match.
        text = unescape(data.decode("utf-8", "replace"))
        text = re.sub(
            r"\\([0-9a-f]{1,6})\s?|\\(.)",
            lambda m: chr(min(int(m[1], 16), 0x10FFFF)) if m[1] else m[2],
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if _SVG_UNSAFE.search(text):
            raise UsageError(f"SVG {src!r} references outside content or has scripts")
        return "image/svg+xml"
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
            fmt = img.format
    except Exception:  # noqa: BLE001
        fmt = None
    if fmt not in MIME:
        raise UsageError(f"{src!r} is not a PNG, JPEG, GIF or SVG image")
    return MIME[fmt]


def _loads(tokens, functions=CSS_LOADERS) -> bool:
    """True when CSS tokens, at any depth, use one of ``functions`` (by default: fetch
    something, url() or an image function)."""
    for t in tokens:
        if (t.type == "url" and functions is CSS_LOADERS) or (
            t.type == "function" and t.lower_name in functions
        ):
            return True
        nested = getattr(t, "arguments", None) or getattr(t, "content", None)
        if isinstance(nested, list) and _loads(nested, functions):
            return True
    return False


def clean_css(css: str) -> str:
    """Keep the style rules, @media and @page of ``<style>`` CSS; refuse anything that loads."""
    out = []
    for rule in tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True):
        if rule.type == "error":
            raise UsageError(f"<style>: invalid CSS ({rule.message})")
        prelude = tinycss2.serialize(rule.prelude).strip()
        at = rule.lower_at_keyword if rule.type == "at-rule" else None
        if _loads(rule.prelude):
            raise UsageError(f"<style>: {prelude!r} loads an external resource")
        if at == "media" and rule.content is not None:
            out.append(f"@media {prelude} {{\n{clean_css(tinycss2.serialize(rule.content))}\n}}")
            continue
        if at not in (None, "page"):
            raise UsageError(f"<style>: @{at} is not allowed; use style rules, @media and @page")
        decls = []
        for d in tinycss2.parse_blocks_contents(
            rule.content or [], skip_comments=True, skip_whitespace=True
        ):
            if d.type != "declaration":
                where = f"@page {prelude}".strip() if at else prelude
                what = f"@{d.at_keyword}" if d.type == "at-rule" else repr(d.serialize().strip())
                raise UsageError(
                    f"<style>: {what} cannot go inside {where!r}; only declarations "
                    "(property: value) can"
                )
            if _loads(d.value) or d.lower_name in ("behavior", "-moz-binding"):
                raise UsageError(
                    f"<style>: {d.serialize().strip()!r} loads an external resource; "
                    "show images with <img>"
                )
            name = d.lower_name
            if name == "clip" or name.startswith(SHAPE_PROPERTIES) or _loads(d.value, CSS_SHAPES):
                raise UsageError(
                    f"<style>: {d.serialize().strip()!r} draws shapes; use colours, borders "
                    "and linear or radial gradients, and show figures with <img>"
                )
            decls.append(d.serialize().strip())
        out.append(f"{'@page ' if at else ''}{prelude} {{ {'; '.join(decls)} }}")
    # `<` is only valid inside CSS strings; escaped, a "</style>" in one cannot close the block.
    return "\n".join(out).replace("<", "\\3c ")


def sanitize(text: str, base: Path, root: Path) -> tuple[str, str, list[Path], list[str]]:
    """Clean report or dashboard HTML to an allowlist and inline every image as a data: URI.

    An ``<img>`` naming a plot skill's ``.html`` becomes a sandboxed frame of that page.
    Returns the body HTML, the cleaned CSS of its ``<style>`` blocks, the local files it
    embeds (in order, once each), and the CSP hashes of the embedded plots' scripts.
    """
    errors: list[str] = []
    images: list[Path] = []
    plots: list[tuple[str, list[str]]] = []
    # Only <style> elements the HTML parser sees; one in a comment or a <textarea> is text.
    styles = nh3.clean(text, tags={"style"}, attributes={}, clean_content_tags=set())
    css = clean_css("\n".join(m.group(1) for m in _STYLE.finditer(styles)))

    def keep(tag, attr, value):
        if tag == "input" and attr == "type" and value.strip().lower() not in INPUT_TYPES:
            errors.append(f'<input type="{value}">: only radio and checkbox inputs are allowed')
            return None
        if attr == "style" and _STYLE_LOADS.search(value):
            errors.append(
                f'<{tag} style="{value}">: inline styles cannot use url(), image functions, '
                "@import or backslash escapes"
            )
            return None
        if tag != "img" or attr != "src":
            return value
        src = value.strip()
        try:
            if src.lower().endswith((".html", ".htm")):
                if re.match(r"^[a-z][a-z0-9+.-]*:|^//", src, re.IGNORECASE):
                    raise UsageError(f"{src!r}: an interactive plot must be a local file")
                path = _local(src, base, root)
                plots.append(_plot_page(path, src))
                # A marker; the whole <img> is swapped for the plot's frame after cleaning.
                uri = f"plot:{len(plots) - 1}"
            else:
                uri, path = _image_data(src, base, root)
        except UsageError as exc:
            errors.append(str(exc))
            return None
        if path is not None and path not in images:
            images.append(path)
        return uri

    body = nh3.clean(
        text,
        tags=TAGS,
        attributes=ATTRIBUTES,
        clean_content_tags=DROP_WITH_CONTENT,
        # data: is left out, so a src or href the author wrote as data: is dropped;
        # only the data: URIs `keep` builds from checked image bytes survive.
        url_schemes=LINK_SCHEMES,
        attribute_filter=keep,
        filter_style_properties=STYLE_PROPERTIES,
        link_rel="noopener noreferrer",
    )
    # The cleaner drops a src outside LINK_SCHEMES (file:, data:, ...) before `keep` sees it,
    # so every <img> and <input> left is parsed for the attribute it needs.
    tags = []
    parser = HTMLParser()
    parser.handle_starttag = lambda tag, attrs: tags.append((tag, dict(attrs)))
    parser.feed(body)
    parser.close()
    if any(tag == "img" and "src" not in attrs for tag, attrs in tags):
        errors.append("<img> needs a src naming a local image file or an https:// URL")
    if any(tag == "input" and "type" not in attrs for tag, attrs in tags):
        errors.append('<input> needs type="radio" or type="checkbox"')
    if errors:
        raise UsageError("; ".join(errors))
    body = re.sub(
        r'<img\b(?:[^>"]|"[^"]*")*?\bsrc="plot:(\d+)"(?:[^>"]|"[^"]*")*>',
        lambda m: _iframe(m[0], plots[int(m[1])][0]),
        body,
    )
    hashes = list(dict.fromkeys(h for _, page_hashes in plots for h in page_hashes))
    return body, css, images, hashes


def document(body: str, title: str, css: str = "", script_hashes=()) -> str:
    # Only the exact scripts of embedded plots may run; they sit in sandboxed frames, which
    # inherit this policy. The page itself has no scripts: cleaning removed them all.
    csp = CSP + (f"; script-src {' '.join(script_hashes)}" if script_hashes else "")
    return (
        '<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{csp}">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n<style>{CSS}</style>\n"
        + (f"<style>\n{css}\n</style>\n" if css else "")
        + "</head>\n"
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def write_pdf(page: str, out: Path) -> None:
    try:
        from weasyprint import HTML, URLFetcher
    except OSError as exc:
        raise DataError(
            f"PDF output needs the Pango library ({exc}); install it "
            "(brew install pango, or apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0) or write .html"
        ) from None

    # After sanitizing every URL is a data: image; refuse anything else rather than fetch it.
    HTML(string=page, url_fetcher=URLFetcher(allowed_protocols={"data"})).write_pdf(out)


@weather_skill(name="report-dashboard", version=_SKILL_VERSION)
@weather_skill.argument(
    "--html",
    required=True,
    help=(
        "The report or dashboard itself, as HTML text (not a file path). Image src paths "
        "are relative to the working directory."
    ),
)
def report_dashboard(html, output, **kwargs):
    """Sanitize a report or dashboard in HTML, embed its images, and write self-contained HTML or PDF."""
    outputs = output if isinstance(output, list) else [output]
    for out in outputs:
        if out.suffix.lower() not in (".html", ".htm", ".pdf"):
            raise UsageError(f"--output {out} must end in .html, .htm or .pdf")
    if "<" not in html:
        raise UsageError("--html takes the page's HTML text, not a file name")
    m = _TITLE.search(html)
    title = unescape(re.sub(r"<[^>]*>", "", m.group(1))).strip() if m else ""
    root = Path.cwd().resolve()
    body, css, images, hashes = sanitize(html, root, root)
    controls = [f"<{t}>" for t in INTERACTIVE if re.search(rf"<{t}\b", body)]
    controls += ["an interactive plot"] * ('<iframe class="plotly"' in body)
    if controls and any(out.suffix.lower() == ".pdf" for out in outputs):
        raise UsageError(
            f"this page is a dashboard ({', '.join(controls)}), which a PDF cannot show; "
            "write .html, or leave out the controls for a printable report"
        )
    page = document(body, title or outputs[0].stem, css, hashes)

    # Provenance comes from the local images only; the HTML text is recorded in args.
    history = build_history(
        "report-dashboard",
        _SKILL_VERSION,
        argparse.Namespace(html=html),
        {},
        images,
        [provenance.load_figure_history(p) or [] for p in images],
        revision=provenance.resolve_skill_revision(__file__),
    )
    # .html first, so a PDF that fails (no Pango) still leaves the HTML written.
    for out in sorted(outputs, key=lambda o: o.suffix.lower() == ".pdf"):
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix.lower() == ".pdf":
            write_pdf(page, out)
        else:
            out.write_text(page, encoding="utf-8")
        provenance.stamp_figure(out, history)
        print(f"Wrote: {out} ({len(images)} local image(s) with provenance)", file=sys.stderr)


if __name__ == "__main__":
    report_dashboard()
