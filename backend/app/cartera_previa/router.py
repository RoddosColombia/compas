# backend/app/cartera_previa/router.py
"""/api/v1/cartera-previa — la carga semanal del cronograma (SUP-4).

El CEO sube el cronograma (los lunes) y COMPAS hace el resto: agrega la cartera ya
originada a la serie semanal que consume el motor y la persiste. Sin tocar la base a
mano y sin engordar la app (se guardan ~80 semanas, no ~9.900 cuotas).

**P4 del ciclo mensual:** la carga NO escribe la META del mes en curso — eso es dato
del CEO. Devuelve los insumos del termómetro (meta vigente vs. colocadas) para que la
desviación se lea aparte, sin contaminar la proyección.

RBAC `proyeccion:gestionar` (mueve la proyección) + `verify_origin`. Fail-closed: un
archivo vacío o con encabezados desconocidos NO pisa la cartera real (422)."""

import os
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.cartera_previa import service
from app.cartera_previa.cronograma import (
    EncabezadosNoReconocidos,
    parsear_cronograma,
)
from app.core.money import money_str
from app.core.time import today_bogota
from app.domain.cartera_previa import CarteraPreviaRecaudo, ColocacionMes
from app.parametros_proyeccion import service as parametros_service
from app.proyeccion.motor import colocacion_mensual

router = APIRouter(prefix="/cartera-previa", tags=["cartera-previa"])

MAX_BYTES = 20 * 1024 * 1024  # el cronograma completo pesa más que una factura


@router.post("/cargar-cronograma")
async def cargar_cronograma(
    archivo: UploadFile,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    """Cronograma real → serie semanal de la cartera ya originada + rampa del mes en
    curso. Devuelve el resumen de lo que cambió (créditos, recaudo futuro, mora real
    medida y colocaciones por mes)."""
    nombre = archivo.filename or "cronograma.xlsx"
    ext = os.path.splitext(nombre)[1].lower()
    if ext != ".xlsx":
        raise HTTPException(
            422, f"extensión '{ext}' no soportada: el cronograma es un .xlsx"
        )
    contenido = await archivo.read(MAX_BYTES + 1)
    if len(contenido) > MAX_BYTES:
        raise HTTPException(422, "el archivo supera el límite de 20 MB")

    try:
        # P5: el mes en curso se proyecta COMPLETO y define el corte de no-solape (los
        # créditos originados dentro de él son del objetivo del mes, no de la serie).
        hoy_bog = today_bogota()
        resumen = parsear_cronograma(
            contenido, hoy=hoy_bog, mes_en_curso=(hoy_bog.year, hoy_bog.month)
        )
    except EncabezadosNoReconocidos as e:
        raise HTTPException(422, str(e)) from e

    # Fail-closed: una carga vacía dejaría la cartera real en cero. Es MUCHO más
    # probable que sea el archivo equivocado que un negocio sin cuotas por cobrar.
    if not resumen.serie:
        raise HTTPException(
            422,
            "el cronograma quedó vacío (sin cuotas por cobrar hacia adelante): no se "
            "pisa la cartera cargada. Verifica que sea el export correcto.",
        )

    # 1. la serie: foto NUEVA (las semanas que ya no existen se van con la vieja)
    nuevas = {f["semana_global"] for f in resumen.serie}
    for vieja in await CarteraPreviaRecaudo.find_all().to_list():
        if vieja.semana_global not in nuevas:
            await vieja.delete()
    await service.cargar_serie(resumen.serie, user.id)

    # 2. P6 — las colocaciones REALES por mes se persisten: son el insumo del
    # TERMÓMETRO de desviación ("llevamos 35 de la meta de 60"). NO entran al motor: la
    # curva proyecta la META. Foto nueva en cada carga.
    for mes_col, unidades in resumen.colocaciones_por_mes.items():
        existente = await ColocacionMes.find_one(ColocacionMes.mes == mes_col)
        if existente is None:
            await ColocacionMes(mes=mes_col, unidades=unidades).insert()
        elif existente.unidades != unidades:
            existente.unidades = unidades
            await existente.save()

    # 3. P4 del ciclo mensual (CEO 2026-08-23) — la carga semanal ya NO escribe la META
    # del mes en curso.
    #
    # SUPERSEDE la automatización de SUP-4, que la dejaba en el REMANENTE hacia la meta
    # (meta − colocadas) y con eso **pisaba el dato del CEO**: agosto-2026 estaba en 70
    # por decisión suya y la carga lo bajó a 35. Es exactamente el error que no se puede
    # repetir ("la formulación no puede pisar el motor ni el dato").
    #
    # La META es dato del CEO (la rampa de Supuestos); si no la fijó, manda lo que el
    # motor proyecta con `motos_base` + crecimiento. Aquí solo se LEE, para devolverla
    # junto a lo colocado y que la pantalla arme la desviación.
    hoy = today_bogota()
    mes_curso = f"{hoy.year:04d}-{hoy.month:02d}"
    params = await parametros_service.obtener_vigente()
    meta_del_mes = (
        params.rampa_unidades.get(
            mes_curso,
            colocacion_mensual(
                params.motos_base,
                params.crec_pct_mensual,
                1,
                None,
                params.crec_pct_mensual_2,
                params.crec_mes_corte,
            )[0],
        )
        if params is not None
        else None
    )

    return {
        "creditos": resumen.creditos,
        "semanas": len(resumen.serie),
        "cuotas_futuras": resumen.cuotas_futuras,
        "recaudo_futuro": money_str(resumen.recaudo_futuro),
        "vencido_sin_pagar": money_str(resumen.vencido_sin_pagar),
        "creditos_en_mora": resumen.creditos_en_mora,
        "colocaciones_por_mes": resumen.colocaciones_por_mes,
        # P4 — insumos del TERMÓMETRO del mes en curso (Paso 2 del contrato): la meta
        # vigente contra lo realmente colocado. La carga NO toca la meta.
        "mes_en_curso": mes_curso,
        "meta_del_mes": meta_del_mes,
        "colocadas_del_mes": resumen.colocaciones_por_mes.get(mes_curso, 0),
        "errores": resumen.errores,
    }


@router.get("/serie")
async def serie(_: User = Depends(require_permission("dashboard:leer"))):
    """La serie vigente (para ver qué tiene el motor hoy). Montos como string."""
    recaudo, activos = await service.obtener_series()
    return {
        "semanas": len(recaudo),
        "recaudo_total": money_str(sum(recaudo.values(), Decimal("0"))),
        "detalle": [
            {
                "semana_global": s,
                "recaudo": money_str(recaudo[s]),
                "n_activos": activos.get(s, 0),
            }
            for s in sorted(recaudo)
        ],
    }
