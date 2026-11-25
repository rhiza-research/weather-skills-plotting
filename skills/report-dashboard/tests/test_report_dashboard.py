"""Correctness tests for report-dashboard."""

import base64
import io
import json
import re

import pytest
from PIL import Image
from skill_conftest import load_skill, run_skill
from weather_skills_core import provenance


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (30, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


PNG = _png()
PLOT_HISTORY = [{"skill": "plot", "version": "1.0", "args": {}, "input": None}]


@pytest.fixture(scope="module")
def mod():
    return load_skill("report-dashboard", "report_dashboard")


@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "figs").mkdir()
    (tmp_path / "figs" / "map.png").write_bytes(PNG)
    provenance.stamp_figure(tmp_path / "figs" / "map.png", PLOT_HISTORY)
    (tmp_path / "figs" / "plain.png").write_bytes(PNG)
    return tmp_path


def _page(body):
    return f"<html><head><title>Rain &amp; wind</title></head><body>{body}</body></html>"


def test_sanitize_keeps_report_markup_and_drops_active_content(mod, work):
    body, css, images, hashes = mod.sanitize(
        "<script>alert(1)</script>"
        '<h2 onclick="x()" class="c">Title</h2>'
        '<p style="color:red; position:fixed; background-image:url(http://x/t.png)">hi</p>'
        '<a href="javascript:alert(1)">bad</a><a href="https://ok.org">ok</a>'
        '<iframe src="https://evil"></iframe><form action="https://x"><button>Go</button></form>'
        '<table><tr><td colspan="2">1</td></tr></table>',
        work,
        work,
    )
    assert "<script" not in body and "alert" not in body
    assert "onclick" not in body and "<iframe" not in body
    assert "<form" not in body and "<button" not in body and "https://x" not in body
    assert '<h2 class="c">Title</h2>' in body
    assert '<p style="color:red">hi</p>' in body
    assert '<a rel="noopener noreferrer">bad</a>' in body
    assert 'href="https://ok.org"' in body
    assert 'colspan="2"' in body
    assert images == [] and css == "" and hashes == []


def test_html_and_pdf_carry_local_image_provenance(mod, work):
    src = _page(
        "<style>h1 { color: #123456 }</style>"
        '<h1>Report</h1><figure><img src="figs/map.png" alt="map"><figcaption>Map</figcaption>'
        '</figure><img src="figs/plain.png"><img src="./figs/map.png">',
    )
    run_skill(mod.report_dashboard, "--html", src, "-o", "out/r.html", "-o", "out/r.pdf")

    page = (work / "out" / "r.html").read_text()
    assert "<title>Rain &amp; wind</title>" in page
    assert page.count('src="data:image/png;base64,') == 3
    assert "figs/" not in page.split("</head>")[1]
    assert "Content-Security-Policy" in page
    assert "h1 { color: #123456 }" in page  # a static report keeps its <style>, PDF too

    for out in ("r.html", "r.pdf"):
        (entry,) = provenance.load_figure_history(work / "out" / out)
        assert entry["skill"] == "report-dashboard"
        assert entry["args"] == {"html": src}
        # Each local image once, in order, with its own history (none for plain.png).
        assert [i["basename"] for i in entry["input"]] == ["map.png", "plain.png"]
        assert entry["input"][0]["history"] == PLOT_HISTORY
        assert entry["input"][1]["history"] == []
    assert (work / "out" / "r.pdf").read_bytes().startswith(b"%PDF")


def test_https_image_is_embedded_without_provenance(mod, work, monkeypatch):
    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda url, timeout: io.BytesIO(PNG))
    src = _page('<img src="https://example.org/logo.png"><img src="figs/map.png">')
    run_skill(mod.report_dashboard, "--html", src, "-o", "r.html")
    page = (work / "r.html").read_text()
    assert (
        page.count("data:image/png;base64,") == 2 and "example.org" not in page.split("<body>")[1]
    )
    # One local image: a plain chain, its history then this step.
    plot, entry = provenance.load_figure_history(work / "r.html")
    assert plot == PLOT_HISTORY[0]
    assert entry["skill"] == "report-dashboard" and entry["input"]["basename"] == "map.png"


@pytest.mark.parametrize(
    ("src", "setup", "message"),
    [
        ("http://example.org/x.png", None, "only local files and https"),
        ("//evil.org/x.png", None, "only local files and https"),
        ("../outside.png", None, "outside the working directory"),
        ("figs/missing.png", None, "not found"),
        ("figs/fake.png", ("figs/fake.png", b"secret text"), "not a PNG"),
        (
            "figs/x.svg",
            (
                "figs/x.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg"><image href="http://e/x"/></svg>',
            ),
            "references outside content",
        ),
        (
            "figs/y.svg",
            (
                "figs/y.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg"><image href=http://e/x /></svg>',
            ),
            "references outside content",
        ),
        ("file:///etc/hosts", None, "needs a src"),
        ("data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=", None, "needs a src"),
        ("plot:0", None, "needs a src"),
    ],
)
def test_refused_images_exit_2(mod, work, capsys, src, setup, message):
    if setup:
        (work / setup[0]).write_bytes(setup[1])
    page = _page(f'<img src="{src}">')
    with pytest.raises(SystemExit) as exc:
        run_skill(mod.report_dashboard, "--html", page, "-o", "r.html")
    assert exc.value.code == 2
    assert message in capsys.readouterr().err
    assert not (work / "r.html").exists()


def test_matplotlib_style_svg_is_accepted(mod, work):
    (work / "figs" / "c.svg").write_text(
        '<?xml version="1.0"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
        '"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n'
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<defs><clipPath id="p"><rect width="9" height="9"/></clipPath></defs>'
        '<use xlink:href="#p"/><rect width="9" height="9" clip-path="url(#p)"/></svg>'
    )
    body, _css, images, _hashes = mod.sanitize('<img src="figs/c.svg">', work, work)
    assert 'src="data:image/svg+xml;base64,' in body
    assert [p.name for p in images] == ["c.svg"]


def test_pdf_renderer_fetches_only_data_uris(mod, tmp_path, monkeypatch):
    import urllib.request

    seen = []
    real = urllib.request.OpenerDirector.open
    monkeypatch.setattr(
        urllib.request.OpenerDirector,
        "open",
        lambda self, req, *a, **k: (
            seen.append(getattr(req, "full_url", req)) or real(self, req, *a, **k)
        ),
    )
    # Unsanitized markup, so the guard itself is what stops the fetch.
    mod.write_pdf(
        '<p style="background-image:url(http://127.0.0.1:9/bg.png)">x</p>'
        '<img src="http://127.0.0.1:9/x.png"><img src="data:image/png;base64,'
        f'{base64.b64encode(PNG).decode()}">',
        tmp_path / "x.pdf",
    )
    assert seen and all(u.startswith("data:") for u in seen)
    assert (tmp_path / "x.pdf").read_bytes().startswith(b"%PDF")


def test_file_name_instead_of_html_exits_2(mod, work, capsys):
    with pytest.raises(SystemExit) as exc:
        run_skill(mod.report_dashboard, "--html", "draft.html", "-o", "r.html")
    assert exc.value.code == 2
    assert "not a file name" in capsys.readouterr().err


def test_rejects_other_output_types(mod, work, capsys):
    page = _page("<p>x</p>")
    with pytest.raises(SystemExit) as exc:
        run_skill(mod.report_dashboard, "--html", page, "-o", "r.docx")
    assert exc.value.code == 2
    assert json.dumps(".pdf")[1:-1] in capsys.readouterr().err


DASHBOARD = (
    "<style>.view { display: none }"
    ' body:has(#lead option[value="w2"]:checked) .w2,'
    ' body:has(#lead option[value="w1"]:checked) .w1 { display: block }</style>'
    '<h1>Outlook</h1><label for="lead">Lead</label>'
    '<select id="lead"><option value="w1" selected>Week 1</option>'
    '<option value="w2">Week 2</option></select>'
    '<figure class="view w1"><img src="figs/map.png"></figure>'
    '<figure class="view w2"><img src="figs/plain.png"></figure>'
    '<input type="radio" name="t" id="t1" checked><label for="t1">Tab</label>'
    "<details open><summary>Method</summary><p>CHIRPS v3.</p></details>"
)


def test_dashboard_keeps_controls_and_style(mod, work):
    run_skill(mod.report_dashboard, "--html", _page(DASHBOARD), "-o", "d.html")
    page = (work / "d.html").read_text()
    for kept in (
        '<select id="lead"><option value="w1" selected="">Week 1</option>',
        '<label for="lead">Lead</label>',
        '<figure class="view w1"><img src="data:image/png;base64,',
        '<input type="radio" name="t" id="t1" checked="">',
        '<details open=""><summary>Method</summary>',
        'body:has(#lead option[value="w1"]:checked) .w1 { display: block }',
    ):
        assert kept in page
    (entry,) = provenance.load_figure_history(work / "d.html")
    assert [i["basename"] for i in entry["input"]] == ["map.png", "plain.png"]


def test_dashboard_refuses_pdf_and_writes_nothing(mod, work, capsys):
    with pytest.raises(SystemExit) as exc:
        run_skill(mod.report_dashboard, "--html", _page(DASHBOARD), "-o", "d.html", "-o", "d.pdf")
    assert exc.value.code == 2
    assert "dashboard (<select>, <input>, <details>)" in capsys.readouterr().err
    assert not (work / "d.html").exists() and not (work / "d.pdf").exists()


@pytest.mark.parametrize(
    ("html", "message"),
    [
        ("<style>.a { background: url(x.png) }</style>", "loads an external resource"),
        ('<style>.a { background-image: image-set("a.png" 1x) }</style>', "external resource"),
        ("<style>.a { --bg: url(https://e/x.png) }</style>", "external resource"),
        ('<style>@import "https://e/x.css";</style>', "@import is not allowed"),
        ("<style>@font-face { font-family: x }</style>", "@font-face is not allowed"),
        ('<input type="password" name="p">', "only radio and checkbox"),
        ('<input name="q">', "needs type"),
    ],
)
def test_refused_css_and_inputs_exit_2(mod, work, capsys, html, message):
    with pytest.raises(SystemExit) as exc:
        run_skill(mod.report_dashboard, "--html", _page(html + "<p>x</p>"), "-o", "r.html")
    assert exc.value.code == 2
    assert message in capsys.readouterr().err


def test_css_string_cannot_close_the_style_block(mod, work):
    css = 'p::after { content: "</style><script>alert(1)</script>" }'
    run_skill(
        mod.report_dashboard, "--html", _page(f"<style>{css}</style><p>x</p>"), "-o", "r.html"
    )
    # The block ends at the first </style>, as in a browser; the rest is cleaned as HTML.
    page = (work / "r.html").read_text()
    assert "<script" not in page
    # A `<` that does reach the CSS is escaped, so it can never open a tag.
    assert (
        mod.clean_css('p::after { content: "<!--</b>" }')
        == r'p::after { content: "\3c !--\3c /b>" }'
    )


def _plot_html(path, skill="plot", body="<script>Plotly.newPlot('p', [])</script>"):
    path.write_text(f'<html><head></head><body><div id="p"></div>{body}</body></html>')
    provenance.stamp_figure(path, [{"skill": skill, "version": "2.0", "args": {}, "input": None}])
    return path


def test_plot_html_becomes_a_sandboxed_frame(mod, work):
    import hashlib

    _plot_html(work / "figs" / "rain.html")
    page_html = _page(
        '<img src="figs/rain.html" alt="Rain map" height="400"><img src="figs/map.png">'
    )
    run_skill(mod.report_dashboard, "--html", page_html, "-o", "d.html")
    page = (work / "d.html").read_text()

    assert '<iframe class="plotly" sandbox="allow-scripts allow-downloads" title="Rain map"' in page
    assert "width: 100%; height: 400px" in page
    assert 'srcdoc="&lt;html&gt;' in page and "&lt;script&gt;Plotly.newPlot(" in page
    # Only the plot's own script may run, through its hash; the page has none of its own.
    digest = base64.b64encode(hashlib.sha256(b"Plotly.newPlot('p', [])").digest()).decode()
    assert f"script-src 'sha256-{digest}'" in page
    assert "<script" not in page
    (entry,) = provenance.load_figure_history(work / "d.html")
    assert [i["basename"] for i in entry["input"]] == ["rain.html", "map.png"]
    assert entry["input"][0]["history"][0]["skill"] == "plot"


def test_page_with_a_plot_refuses_pdf(mod, work, capsys):
    _plot_html(work / "figs" / "rain.html")
    with pytest.raises(SystemExit) as exc:
        run_skill(
            mod.report_dashboard, "--html", _page('<img src="figs/rain.html">'), "-o", "r.pdf"
        )
    assert exc.value.code == 2
    assert "dashboard (an interactive plot)" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda p: p.write_text("<html><script>x()</script></html>"), "written by the plot skill"),
        (lambda p: _plot_html(p, skill="report-dashboard"), "written by the plot skill"),
        (
            lambda p: _plot_html(p, body='<script src="https://cdn.plot.ly/x.js"></script>'),
            "inline",
        ),
    ],
)
def test_refused_html_figures_exit_2(mod, work, capsys, make, message):
    make(work / "figs" / "x.html")
    with pytest.raises(SystemExit) as exc:
        run_skill(mod.report_dashboard, "--html", _page('<img src="figs/x.html">'), "-o", "r.html")
    assert exc.value.code == 2
    assert message in capsys.readouterr().err


# Rule: the --html text cannot draw with drawing elements, load pictures, or run code.
@pytest.mark.parametrize(
    "html",
    [
        '<svg width="9" height="9"><rect width="9" height="9" fill="red"/></svg>',
        "<svg><foreignObject><div>hi</div></foreignObject></svg>",
        '<canvas width="9" height="9"></canvas>',
        "<math><mi>x</mi></math>",
        '<object data="figs/map.png"></object><embed src="figs/map.png">',
        '<picture><source srcset="figs/map.png"></picture>',
        '<video src="v.mp4" poster="figs/map.png"></video><audio src="a.mp3"></audio>',
        '<p style="background-image: url(data:image/png;base64,AAAA)">t</p>',
        '<meta http-equiv="refresh" content="0"><base href="https://e/"><link href="x.css">',
        '<details ontoggle="x()"><summary onclick="x()">s</summary></details>',
        "<noscript><p>n</p></noscript><template><p>t</p></template>",
    ],
)
def test_html_cannot_use_drawing_or_script_elements(mod, work, html):
    body, _css, images, hashes = mod.sanitize(html, work, work)
    assert not re.search(
        r"<(svg|canvas|math|object|embed|picture|source|video|audio|script|meta|base|link)\b"
        r"|\bon\w+=|srcset|data:|url\(",
        body,
        re.IGNORECASE,
    ), body
    assert images == [] and hashes == []


# Rule: a linked file can run scripts only if it is the plot skill's HTML.
@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("a.svg", '<svg xmlns="http://www.w3.org/2000/svg" onload="x()"/>', "has scripts"),
        ("b.svg", '<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script></svg>', "scripts"),
        ("c.png", "<html><script>x()</script></html>", "not a PNG"),
        ("d.html", "<html><script>x()</script></html>", "written by the plot skill"),
    ],
)
def test_linked_files_cannot_bring_scripts(mod, work, capsys, name, content, message):
    (work / "figs" / name).write_text(content)
    with pytest.raises(SystemExit) as exc:
        run_skill(mod.report_dashboard, "--html", _page(f'<img src="figs/{name}">'), "-o", "r.html")
    assert exc.value.code == 2
    assert message in capsys.readouterr().err


def test_remote_html_is_refused(mod, work, capsys):
    with pytest.raises(SystemExit):
        run_skill(
            mod.report_dashboard,
            "--html",
            _page('<img src="https://e.org/p.html">'),
            "-o",
            "r.html",
        )
    assert "an interactive plot must be a local file" in capsys.readouterr().err


def test_style_keeps_colours_and_linear_radial_gradients(mod):
    css = (
        ".band { background: linear-gradient(90deg, #0b3d5c, #2a7ab0) }"
        " .glow { background: radial-gradient(circle at top, #fff, #e8f0f7) }"
        " .card { border-radius: 8px; box-shadow: 0 1px 3px #0003; background-color: #f6f8fa }"
    )
    assert mod.clean_css(css).count("{") == 3


@pytest.mark.parametrize(
    "css",
    [
        ".pie { background: conic-gradient(#c00 0 35%, #06c 0) }",
        ".pie { background: repeating-conic-gradient(red 0 10%, blue 0 20%) }",
        ".line { clip-path: polygon(0 100%, 10% 60%, 20% 70%) }",
        '.line { -webkit-clip-path: path("M0 0 L10 10") }',
        ".m { mask: linear-gradient(red, blue) }",
        ".m { -webkit-mask-image: radial-gradient(red, blue) }",
        ".s { shape-outside: circle(50%) }",
        '.o { offset-path: path("M0 0") }',
        ".c { clip: rect(0, 10px, 10px, 0) }",
        "@media print { .pie { background: conic-gradient(red, blue) } }",
    ],
)
def test_style_cannot_draw_pies_or_shapes(mod, css):
    with pytest.raises(mod.UsageError, match="draws shapes"):
        mod.clean_css(css)
