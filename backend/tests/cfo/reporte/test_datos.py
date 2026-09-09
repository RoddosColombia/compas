import pytest
from app.cfo.reporte import datos as D
from app.cfo.reporte.modelos import DatosReporte


@pytest.mark.asyncio
async def test_reunir_datos_arma_secciones_y_rumbo(monkeypatch):
    async def fake_proy(**k):
        return {
            "caja_minima": "1000000",
            "caja_atencion": "3000000",
            "piso_caja": "1200000",
            "meses": [
                {"mes": "2026-09", "caja": "5000000", "estado": "ok"},
                {"mes": "2026-10", "caja": "4200000", "estado": "atencion"},
            ],
        }

    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)

    async def fake_consultar(pregunta, *, actor_id, cliente=None, historial=None):
        from app.cfo.agente.modelos import RespuestaCFO, UsoLLM

        return RespuestaCFO(
            texto="Resumen narrado con $5.000.000.",
            abstuvo=False,
            texto_crudo="Resumen narrado con [[x]].",
            uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1),
        )

    monkeypatch.setattr(D.servicio, "consultar", fake_consultar)
    # las demás lecturas (mix/gasto/iva/motos) se fakean o se dejan abstenerse — el
    # test verifica la ESTRUCTURA + el rumbo + el resumen narrado.

    datos = await D.reunir_datos(periodo=None)
    assert isinstance(datos, DatosReporte)
    assert datos.periodo  # 'YYYY-MM' del mes vigente (now_bogota)
    assert datos.rumbo is not None and datos.rumbo.caja_minima == "1000000"
    assert datos.rumbo.caja_atencion == "3000000"
    assert datos.rumbo.meses == ["2026-09", "2026-10"]
    assert datos.rumbo.caja == ["5000000", "4200000"]
    assert "5.000.000" in datos.resumen_ejecutivo

    titulos = [s.titulo for s in datos.secciones]
    assert titulos == [
        "Caja y rumbo al umbral",
        "Ventas / colocación",
        "Gasto y eficiencia",
        "Deuda / obligaciones",
    ]

    seccion_caja = next(s for s in datos.secciones if s.titulo.startswith("Caja"))
    cifras_caja = {c.etiqueta: c.valor for c in seccion_caja.cifras}
    # el piso y el mes de quiebre vienen de la MISMA proyección fake ya fetcheada
    assert cifras_caja["Piso de caja proyectado"] == "1200000.00"
    assert cifras_caja["Mes de quiebre del umbral"] == "2026-10"

    # ninguna sección revienta ni deja cifras a medias: cada Cifra.valor es texto
    for s in datos.secciones:
        for c in s.cifras:
            assert isinstance(c.valor, str)
            assert c.valor != ""


@pytest.mark.asyncio
async def test_sin_proyeccion_abstiene_rumbo(monkeypatch):
    from app.proyeccion.service import ProyeccionError

    async def fake_proy(**k):
        raise ProyeccionError("sin config", 409)

    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)

    async def fake_consultar(*a, **k):
        from app.cfo.agente.modelos import RespuestaCFO, UsoLLM

        return RespuestaCFO(
            texto="Sin proyección disponible.",
            abstuvo=True,
            texto_crudo="…",
            uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1),
        )

    monkeypatch.setattr(D.servicio, "consultar", fake_consultar)

    datos = await D.reunir_datos(periodo=None)
    assert datos.rumbo is None  # sin proyección ⇒ sin serie ⇒ sin gráfica

    seccion_caja = next(s for s in datos.secciones if s.titulo.startswith("Caja"))
    cifras_caja = {c.etiqueta: c.valor for c in seccion_caja.cifras}
    assert cifras_caja["Piso de caja proyectado"] == "sin datos"
    assert cifras_caja["Mes de quiebre del umbral"] == "sin datos"


@pytest.mark.asyncio
async def test_reunir_datos_usa_periodo_explicito(monkeypatch):
    from app.proyeccion.service import ProyeccionError

    async def fake_proy(**k):
        raise ProyeccionError("sin config", 409)

    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)

    async def fake_consultar(*a, **k):
        from app.cfo.agente.modelos import RespuestaCFO, UsoLLM

        return RespuestaCFO(
            texto="ok",
            abstuvo=True,
            texto_crudo="ok",
            uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1),
        )

    monkeypatch.setattr(D.servicio, "consultar", fake_consultar)

    datos = await D.reunir_datos(periodo="2026-01")
    assert datos.periodo == "2026-01"
