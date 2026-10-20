"""FABS · modelos del reporte a inversionistas (inc6 #3). Pydantic strict; los
montos siempre viajan como str (money_str es-CO), nunca number."""

from pydantic import BaseModel, ConfigDict


class Cifra(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    etiqueta: str
    valor: str  # money_str es-CO o texto; NUNCA number


class Seccion(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    titulo: str
    cifras: list[Cifra]


class RumboSerie(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    meses: list[str]
    caja: list[str]  # money_str por mes (para la gráfica)
    caja_minima: str
    caja_atencion: str | None = None


class DatosReporte(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    periodo: str  # 'YYYY-MM'
    resumen_ejecutivo: str  # narrado por FABS (ya verificado/sustituido)
    secciones: list[Seccion]
    rumbo: RumboSerie | None = None  # None ⇒ sin proyección ⇒ sin gráfica
