# backend/app/cartera_previa/router.py
"""/api/v1/cartera-previa — la carga semanal del cronograma (SUP-4).

El CEO sube el cronograma (los lunes) y COMPAS hace el resto: agrega la cartera ya
originada a la serie semanal que consume el motor, la persiste, y deja la rampa del
MES EN CURSO en el remanente hacia la meta. Sin tocar la base a mano y sin engordar
la app (se guardan ~80 semanas, no ~9.900 cuotas).

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
    rampa_mes_en_curso,
)
from app.core.money import money_str
from app.core.time import today_bogota
from app.domain.cartera_previa import CarteraPreviaRecaudo
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
        resumen = parsear_cronograma(contenido, hoy=today_bogota())
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

    # 2. la rampa del MES EN CURSO = remanente hacia la meta (criterio CEO)
    rampa: dict[str, int] = {}
    params = await parametros_service.obtener_vigente()
    if params is not None:
        hoy = today_bogota()
        mes = (hoy.year, hoy.month)
        # la meta del mes es lo que el motor proyectaría sin rampa para ese mes
        meta = colocacion_mensual(
            params.motos_base,
            params.crec_pct_mensual,
            1,
            None,
            params.crec_pct_mensual_2,
            params.crec_mes_corte,
        )[0]
        rampa = rampa_mes_en_curso(resumen.colocaciones_por_mes, mes, meta)
        campos = params.model_dump(exclude={"id", "vigente_desde", "modificado_por"})
        # se conservan las rampas de otros meses que el CEO haya fijado a mano
        campos["rampa_unidades"] = {**params.rampa_unidades, **rampa}
        await parametros_service.actualizar(
            vigente_desde=params.vigente_desde,
            campos=campos,
            usuario_id=user.id,
            nota=(
                f"Carga semanal del cronograma: {resumen.creditos} créditos, "
                f"{money_str(resumen.recaudo_futuro)} por cobrar. La rampa del mes en "
                f"curso queda en el remanente hacia la meta ({rampa})."
            ),
        )

    return {
        "creditos": resumen.creditos,
        "semanas": len(resumen.serie),
        "cuotas_futuras": resumen.cuotas_futuras,
        "recaudo_futuro": money_str(resumen.recaudo_futuro),
        "vencido_sin_pagar": money_str(resumen.vencido_sin_pagar),
        "creditos_en_mora": resumen.creditos_en_mora,
        "colocaciones_por_mes": resumen.colocaciones_por_mes,
        "rampa_mes_en_curso": rampa,
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
