# backend/tests/test_proyeccion_version.py
"""RF-F2 — versión inmutable de la proyección: persistencia (flip vigente, secuencia,
una sola vigente) y diff contra la vigente. Motor NO se toca (esto vive sobre la serie
ya serializada)."""

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.proyeccion_version import ProyeccionVersion
from app.proyeccion.versionado import (
    _persistir_version,
    diff_contra_vigente,
    version_vigente,
)
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield


def _serie(piso="100000000", mes="2027-05", caja_min="125000000"):
    return {
        "escenario": "base",
        "caja_minima": caja_min,
        "piso_caja": piso,
        "mes_mas_ajustado": mes,
        "horizonte_meses": 176,
        "meses": [{"mes": "2026-05", "caja": "24000000"}],
    }


@pytest.mark.asyncio
async def test_primera_version_es_1_y_vigente(db):
    v = await _persistir_version(
        serie=_serie(), valles=[], mes_aprobado="2026-08-01", usuario_id="u1"
    )
    assert v.version == 1
    assert v.vigente is True
    assert v.piso_caja == "100000000"
    assert v.mes_mas_ajustado == "2027-05"
    assert v.serie["meses"][0]["caja"] == "24000000"  # serie fiel


@pytest.mark.asyncio
async def test_segunda_version_incrementa_y_apaga_la_anterior(db):
    await _persistir_version(
        serie=_serie(piso="100000000"),
        valles=[],
        mes_aprobado="2026-08-01",
        usuario_id="u1",
    )
    v2 = await _persistir_version(
        serie=_serie(piso="150000000"),
        valles=[],
        mes_aprobado="2026-09-01",
        usuario_id="u1",
    )
    assert v2.version == 2
    vigentes = await ProyeccionVersion.find(
        ProyeccionVersion.vigente == True  # noqa: E712
    ).to_list()
    assert len(vigentes) == 1 and vigentes[0].version == 2
    total = await ProyeccionVersion.find().count()
    assert total == 2  # la anterior NO se borra (append-only)


@pytest.mark.asyncio
async def test_version_vigente_devuelve_la_ultima(db):
    assert await version_vigente() is None
    await _persistir_version(
        serie=_serie(), valles=[], mes_aprobado="2026-08-01", usuario_id="u1"
    )
    await _persistir_version(
        serie=_serie(), valles=[], mes_aprobado="2026-09-01", usuario_id="u1"
    )
    v = await version_vigente()
    assert v is not None and v.version == 2


@pytest.mark.asyncio
async def test_diff_contra_vigente_piso_y_valles(db):
    anterior = await _persistir_version(
        serie=_serie(piso="100000000", mes="2027-05"),
        valles=[{"mes": "2027-05"}],
        mes_aprobado="2026-08-01",
        usuario_id="u1",
    )
    actual = _serie(piso="130000000", mes="2027-06")
    d = diff_contra_vigente(actual, [{"mes": "2027-06"}, {"mes": "2028-01"}], anterior)
    assert d["hay_anterior"] is True
    assert d["version_anterior"] == 1
    assert d["piso"]["anterior"] == "100000000"
    assert d["piso"]["actual"] == "130000000"
    assert d["piso"]["delta"] == "30000000.00"  # 130M − 100M, Decimal
    assert d["mes_mas_ajustado"]["anterior"] == "2027-05"
    assert d["mes_mas_ajustado"]["actual"] == "2027-06"
    assert d["valles"]["anterior"] == 1 and d["valles"]["actual"] == 2


def test_diff_sin_anterior_lo_dice():
    d = diff_contra_vigente(_serie(), [], None)
    assert d["hay_anterior"] is False


# ─────────────────────── RF-F3 · P3b — valle más profundo ───────────────────────


@pytest.mark.asyncio
async def test_p3b_detecta_valle_mas_profundo_mismo_mes(db):
    """Un valle en el MISMO mes con caja MENOR que la aprobada anterior es 'más
    profundo'. Se reporta con delta negativo (menos caja = más hondo)."""
    anterior = await _persistir_version(
        serie=_serie(),
        valles=[{"mes": "2027-05", "caja": "100000000"}],
        mes_aprobado="2026-08-01",
        usuario_id="u1",
    )
    d = diff_contra_vigente(
        _serie(),
        [{"mes": "2027-05", "caja": "80000000"}],  # 20M más hondo
        anterior,
    )
    assert d["valles"]["mas_profundos"] == [
        {
            "mes": "2027-05",
            "anterior": "100000000",
            "actual": "80000000",
            "delta": "-20000000.00",
        }
    ]


@pytest.mark.asyncio
async def test_p3b_ignora_valle_igual_o_menos_profundo(db):
    """Mismo mes pero caja ≥ anterior no es 'más profundo' — solo se reporta cuando
    empeora. Empatar tampoco cuenta (evita ruido)."""
    anterior = await _persistir_version(
        serie=_serie(),
        valles=[
            {"mes": "2027-05", "caja": "100000000"},
            {"mes": "2027-11", "caja": "80000000"},
        ],
        mes_aprobado="2026-08-01",
        usuario_id="u1",
    )
    d = diff_contra_vigente(
        _serie(),
        [
            {"mes": "2027-05", "caja": "100000000"},  # igual → no
            {"mes": "2027-11", "caja": "90000000"},  # subió → no
        ],
        anterior,
    )
    assert d["valles"]["mas_profundos"] == []


@pytest.mark.asyncio
async def test_p3b_valle_nuevo_no_cuenta_como_mas_profundo(db):
    """Un valle NUEVO (mes no estaba antes) se reporta solo en `nuevos`, no en
    `mas_profundos` — son categorías disjuntas para no doble-contar en la UI."""
    anterior = await _persistir_version(
        serie=_serie(),
        valles=[{"mes": "2027-05", "caja": "100000000"}],
        mes_aprobado="2026-08-01",
        usuario_id="u1",
    )
    d = diff_contra_vigente(
        _serie(),
        [
            {"mes": "2027-05", "caja": "100000000"},  # sin cambio
            {"mes": "2028-01", "caja": "70000000"},  # NUEVO
        ],
        anterior,
    )
    assert d["valles"]["nuevos"] == ["2028-01"]
    assert d["valles"]["mas_profundos"] == []


@pytest.mark.asyncio
async def test_snapshot_aprobada_corre_proyeccion_y_persiste(db, monkeypatch):
    """Verifica el wrapper que dispara el HOOK del router de aprobación: corre la
    proyección vigente + valles y deja una versión vigente en la BD."""
    from app.proyeccion import service as proy_service
    from app.proyeccion.versionado import snapshot_version_aprobada

    async def _fake_proyectar_vigente(*, escenario, mes_inicio, horizonte_meses):
        assert escenario == "base"
        assert mes_inicio == (2026, 8)
        return _serie(piso="99999999", mes="2027-04")

    async def _fake_valles_vigente(*, escenario, mes_inicio, horizonte_meses):
        return {"valles": [{"mes": "2027-04"}]}

    monkeypatch.setattr(proy_service, "proyectar_vigente", _fake_proyectar_vigente)
    monkeypatch.setattr(proy_service, "valles_vigente", _fake_valles_vigente)

    v = await snapshot_version_aprobada(
        mes_aprobado="2026-08-01", usuario_id="u1", mes_inicio=(2026, 8)
    )
    assert v.version == 1
    assert v.vigente is True
    assert v.mes_aprobado == "2026-08-01"
    assert v.piso_caja == "99999999"
    # el valle del reporte quedó guardado en la versión
    assert v.valles == [{"mes": "2027-04"}]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
