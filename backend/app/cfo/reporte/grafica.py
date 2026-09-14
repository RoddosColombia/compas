"""FABS · gráfica rumbo de caja para reporte (matplotlib Agg no-interactivo).

PURO: RumboSerie in, PNG bytes out. matplotlib se importa PEREZOSAMENTE (pesada;
no cargarla al arrancar web). NOTA regla 1: Decimal ya calculados por COMPAS se
pasan a float SOLO para geometría del render — no es cálculo ni display de dinero;
cifras autoritativas van en tablas del .docx como money_str."""

from decimal import Decimal
from io import BytesIO

from app.cfo.reporte.modelos import RumboSerie


def render_rumbo(rumbo: RumboSerie) -> bytes:
    import matplotlib

    matplotlib.use("Agg")  # server-side, sin display
    import matplotlib.pyplot as plt

    xs = list(range(len(rumbo.meses)))
    # float SOLO para geometría (ver docstring)
    ys = [float(Decimal(v)) for v in rumbo.caja]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(xs, ys, marker="o", label="Caja proyectada")
    ax.axhline(
        float(Decimal(rumbo.caja_minima)),
        linestyle="--",
        color="#b91c1c",
        label="Umbral crítico",
    )
    if rumbo.caja_atencion is not None:
        ax.axhline(
            float(Decimal(rumbo.caja_atencion)),
            linestyle=":",
            color="#b45309",
            label="Umbral de atención",
        )
    ax.set_xticks(xs)
    ax.set_xticklabels(rumbo.meses, rotation=45, ha="right")
    ax.set_ylabel("Caja (COP)")
    ax.set_title("Rumbo de caja hacia el umbral")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return buf.getvalue()
