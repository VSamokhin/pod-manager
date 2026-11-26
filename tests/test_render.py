"""Unit tests for template rendering and outline tracing."""

from types import SimpleNamespace

import numpy as np
import pytest

from app import outline, render


def _img() -> SimpleNamespace:
    return SimpleNamespace(id=0, width=400, height=200, stored_filename="x.png")


def test_normalize_coerces_and_rejects_bad_values():
    p = render.normalize(
        {
            "padding": "abc",
            "border_width": "500",
            "cutline": "on",
            "outline_mode": "spiral",
            "background": "red; evil",
            "title_text": "x" * 500,
            "unknown": 1,
        }
    )
    assert p["padding"] == render.DEFAULT_PARAMS["padding"]
    assert p["border_width"] == 200.0
    assert p["cutline"] is True
    assert p["outline_mode"] == "none"
    assert p["background"] == render.DEFAULT_PARAMS["background"]
    assert len(p["title_text"]) == 200
    assert "unknown" not in p


@pytest.mark.parametrize("position", ["top", "bottom", "overlay-top", "overlay-bottom"])
@pytest.mark.parametrize("align", ["start", "middle", "end"])
def test_title_positions(position, align):
    svg, w, h = render.compose_svg(
        _img(), {"title_text": "<b>{title}</b>", "title_position": position, "title_align": align}, href="x", title="T"
    )
    assert "&lt;b&gt;T&lt;/b&gt;" in svg
    assert f'text-anchor="{align}"' in svg
    assert w > 400
    assert h >= 200


def test_rect_outline_cutline_and_rounding():
    params = {"outline_mode": "rect", "outline_width": 2, "outline_offset": 1, "cutline": True, "image_radius": 5}
    svg, _, _ = render.compose_svg(_img(), params, href="x")
    assert svg.count("<rect") >= 4
    assert "clipPath" in svg
    assert "#ff00ff" in svg


def test_cutline_without_outline_and_transparent_background():
    svg, _, _ = render.compose_svg(_img(), {"cutline": True, "background_transparent": True}, href="x")
    assert 'fill="#ffffff"' not in svg
    assert "#ff00ff" in svg


def test_physical_size_and_export_formats():
    svg, w, h = render.compose_svg(_img(), {"border_width": 1}, href="data:,")
    sized, wmm, _ = render.with_physical_size(svg, w, h, None, 254)
    assert wmm == pytest.approx(w / 10)
    assert 'mm"' in sized
    for fmt in ("svg", "pdf", "png"):
        data, _ = render.export(svg, w, h, fmt, 50, 100)
        assert data
    with pytest.raises(ValueError, match="Unknown format"):
        render.export(svg, w, h, "gif", None, 300)


def test_trace_square_and_diagonal_pixels():
    mask = np.zeros((20, 20), dtype=bool)
    mask[5:15, 5:15] = True
    mask[0, 0] = mask[1, 1] = True  # diagonal touch, below min_area -> dropped
    polys = outline.trace(mask, min_area=8)
    assert len(polys) == 1
    xs, ys = polys[0][:, 0], polys[0][:, 1]
    assert (xs.min(), xs.max(), ys.min(), ys.max()) == (5, 15, 5, 15)
    path = outline.smooth_path(polys[0], lambda p: f"{p[0]:.1f},{p[1]:.1f}")
    assert path.startswith("M")
    assert path.endswith("Z")


def test_trace_empty_and_two_islands():
    assert outline.trace(np.zeros((5, 5), dtype=bool)) == []
    mask = np.zeros((10, 30), dtype=bool)
    mask[2:8, 2:8] = True
    mask[2:8, 20:28] = True
    assert len(outline.trace(mask)) == 2
