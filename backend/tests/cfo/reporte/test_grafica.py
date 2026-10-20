from app.cfo.reporte.grafica import render_rumbo
from app.cfo.reporte.modelos import RumboSerie


def test_render_rumbo_devuelve_png():
    r = RumboSerie(
        meses=["2026-09", "2026-10", "2026-11"],
        caja=["5000000", "4200000", "3100000"],
        caja_minima="1000000",
        caja_atencion="3000000",
    )
    png = render_rumbo(r)
    assert isinstance(png, bytes) and png[:8] == b"\x89PNG\r\n\x1a\n"  # magic PNG
    assert len(png) > 100
