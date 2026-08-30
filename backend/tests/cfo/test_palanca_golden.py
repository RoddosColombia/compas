# backend/tests/cfo/test_palanca_golden.py
"""FABS · golden inc4 rebanada 2 (Task 5) — `impacto_palanca_raw` (Task 1) corrida
REAL de punta a punta: motor paramétrico → E1 (anclaje) → D2 (reconciliación), dos
veces (`piso_sin`/`piso_con`), sobre una base de datos mongomock VACÍA (sin anclas,
sin facturas, sin cartera previa — la "base bit a bit" que documenta
`_resultado_con`). Lo único fakeado es la CARGA de configuración vigente:
`parametros_service.obtener_vigente` y `modelos_service.listar_modelos` —
exactamente como pide el brief de Task 5 (no fakear `_resultado_con` como sí hace
`test_impacto_palanca_raw.py`, que es un test de UNIDAD de la orquestación; este es
el golden de INTEGRACIÓN de la matemática real).

Mecanismo (candado de dirección, verificado con un experimento — no adivinado):
`recaudo_credito_mensual` (`app/proyeccion/motor.py`) cuenta, para cada semana `w`,
cuántas motos siguen "activas" (pagando) con `_activos_en_semana(altas, w, plazo)` =
colocadas en la ventana `(w − plazo, w]`, y multiplica esa cuenta por
`cuota_semanal` (que NO cambia en este golden). Si el plazo de una cohorte es CORTO
frente al horizonte proyectado, esa cohorte "se gradúa" (deja de pagar) antes de
tiempo y el recaudo de los meses posteriores cae; si el plazo es más LARGO, esa
misma cohorte sigue activa más semanas y el recaudo de esos meses es mayor. Esto
solo se nota si el plazo BASE es corto en relación con el número de semanas
transcurridas hasta el mes de menor caja (`mes_quiebre`, aquí 2027-01, ≈17 semanas
desde el arranque en 2026-09): con un plazo base ≥ esas ~17 semanas (se probó con
40 y 52) las dos corridas (piso_sin/piso_con) dan IDÉNTICO resultado — nadie se ha
graduado todavía en ninguna de las dos, así que el cambio de palanca es degenerado.
Por eso este golden usa un plazo BASE corto (12 semanas, bien dentro de la ventana
"< 17 semanas" donde el efecto es real) subiendo a 78 — un cambio grande y
significativo, no una degeneración de 1 semana. `cuota_semanal` no se toca; el
costo de adquisición (Auteco/`pago_inventario`) tampoco depende de `plazo_semanas`
en `motor.py`, así que un recaudo mayor con costos iguales implica un piso de caja
proyectado MAYOR: se espera `piso_con > piso_sin` (estricto: el escenario elegido
es deliberadamente no-degenerado) y por lo tanto
`impacto = piso_con - piso_sin > 0`.

Los valores exactos de `piso_sin`/`piso_con`/`mes_quiebre` no se pueden derivar a
mano (dependen de la composición completa motor→E1→D2 sobre 12 meses) — se
CONGELAN aquí tras observarlos una vez (ejecutando este mismo escenario con un
script de exploración fuera del test, ver Task 5 report). Lo que este test SÍ
garantiza independientemente de esos números congelados es (a) la dirección del
signo (arriba, con la explicación mecánica) y (b) la identidad de reconciliación
`impacto == piso_con - piso_sin`, así que una regresión que invierta el signo o
rompa la resta se atrapa aunque alguien "actualice" los valores congelados sin
pensar."""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.modelo_moto import ModeloMoto
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.proyeccion import service as svc
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

_MES_INICIO = (2026, 9)
_HORIZONTE = 12
_PLAZO_BASE = 12  # corto a propósito (ver docstring del módulo: evita el degenerado)
_PLAZO_NUEVO = Decimal("78")


async def _aw(value):
    """Coroutine mínima que resuelve a `value` (monkeypatch de funciones async)."""
    return value


def _vig() -> ParametrosProyeccion:
    """`ParametrosProyeccion` real (mismo patrón que `test_e1_pipeline.py::_params` /
    `test_impacto_palanca_raw.py::_vig`), con crecimiento en 0 para que el único
    driver del cambio semana a semana sea la ventana de `plazo_semanas` — no una
    rampa de altas que se mezcle con el efecto que este golden quiere aislar."""
    return ParametrosProyeccion(
        vigente_desde="2026-09-01",
        caja_inicial=Decimal("50000000"),
        caja_minima=Decimal("10000000"),
        motos_base=20,
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=_HORIZONTE,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=60,
        base_auteco_dias=30,
        tasa_auteco=Decimal("0.016"),
        gastos_fijos=Decimal("2000000"),
        gps_moto=Decimal("0"),
        costo_moto_nueva=Decimal("0"),
        deuda=Decimal("0"),
        tasa_deuda=Decimal("0"),
        mes_inicio_deuda=0,
        meses_deuda=0,
        pct_mora=Decimal("0"),
        pct_recuperacion=Decimal("0"),
        pct_default=Decimal("0"),
        pct_provision=Decimal("0"),
    )


def _modelos(plazo: int) -> list[ModeloMoto]:
    """Un único modelo (mix=1): el resultado no depende de cómo se reparte el mix
    entre varios modelos, solo del cambio de `plazo_semanas`."""
    return [
        ModeloMoto(
            nombre="Raider",
            costo_auteco=Decimal("3000000"),
            precio_venta_con_iva=Decimal("4500000"),
            cuota_inicial=Decimal("500000"),
            cuota_semanal=Decimal("80000"),
            plazo_semanas=plazo,
            matricula=Decimal("0"),
            participacion_mix=Decimal("1"),
            orden=1,
        )
    ]


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


@pytest.mark.asyncio
async def test_golden_plazo_12_a_78_todos(db, monkeypatch):
    """Golden congelado: `impacto_palanca_raw` REAL (motor→E1→D2, dos corridas) con
    plazo_semanas 12→78 en el único modelo del catálogo. Solo se fakea la carga de
    config vigente (`parametros_service.obtener_vigente` / `modelos_service.
    listar_modelos`) — el resto de la tubería (arranque de caja, cartera previa, IVA
    proyectado, anclaje, reconciliación) corre real sobre una DB mongomock vacía."""
    monkeypatch.setattr(svc.parametros_service, "obtener_vigente", lambda: _aw(_vig()))
    monkeypatch.setattr(
        svc.modelos_service,
        "listar_modelos",
        lambda activo=True: _aw(_modelos(_PLAZO_BASE)),
    )

    out = await svc.impacto_palanca_raw(
        palanca="plazo_semanas",
        nuevo_valor=_PLAZO_NUEVO,
        modelo="todos",
        escenario="base",
        mes_inicio=_MES_INICIO,
        horizonte_meses=_HORIZONTE,
    )

    # --- candado de DIRECCIÓN (independiente de los valores congelados abajo) ---
    # Plazo base corto (12 sem) vs. horizonte (12 meses ≈52 sem): con el plazo corto
    # las cohortes tempranas se "gradúan" (dejan de pagar) antes de que termine el
    # horizonte, así que el recaudo cae frente al caso con plazo largo (78 sem), donde
    # las mismas cohortes siguen activas. El costo de adquisición no depende de
    # plazo_semanas -> más recaudo con mismo costo = piso de caja proyectado MAYOR.
    assert out.piso_con > out.piso_sin
    assert out.impacto > Decimal("0")

    # --- identidad de reconciliación (misma tubería, no una resta inventada aparte) ---
    assert out.impacto == out.piso_con - out.piso_sin

    # --- valores CONGELADOS (observados una vez corriendo este mismo escenario; ver
    # docstring del módulo: el candado real es la dirección + la identidad arriba,
    # esto solo atrapa una regresión numérica silenciosa en el pipeline) ---
    assert out.piso_sin == Decimal("-259120000.00")
    assert out.piso_con == Decimal("-23760000.00")
    assert out.impacto == Decimal("235360000.00")
    assert out.mes_quiebre == "2027-01"
