# backend/app/proyeccion/versionado.py
"""RF-F2 — versionado de la serie de proyección (capa sobre `_serializar`; motor OK).

Al aprobar el presupuesto se CONGELA la proyección base a horizonte completo como una
`ProyeccionVersion` inmutable (post-commit, best-effort). Las vistas comparan la
proyección actual contra la última versión aprobada (piso y valles).

Separación:
  · `_persistir_version` — lógica de BD pura (flip vigente, secuencia). Testeable.
  · `snapshot_version_aprobada` — corre la proyección vigente y persiste.
  · `diff_contra_vigente` — puro, compara actual vs. la vigente.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.money import money_str
from app.domain.proyeccion_version import ProyeccionVersion


async def _persistir_version(
    *,
    serie: dict,
    valles: list[dict],
    mes_aprobado: str,
    usuario_id: str,
) -> ProyeccionVersion:
    """Inserta la versión nueva (máx+1, vigente) y apaga la anterior (append-only:
    su `serie` nunca se sobrescribe, solo el puntero `vigente`)."""
    ultima = (
        await ProyeccionVersion.find().sort(-ProyeccionVersion.version).first_or_none()
    )
    if ultima is not None and ultima.vigente:
        ultima.vigente = False
        await ultima.save()

    nueva = ProyeccionVersion(
        version=(ultima.version + 1) if ultima is not None else 1,
        vigente=True,
        mes_aprobado=mes_aprobado,
        escenario=serie.get("escenario", "base"),
        horizonte_meses=int(
            serie.get("horizonte_meses") or len(serie.get("meses", []))
        ),
        serie=serie,
        piso_caja=str(serie["piso_caja"]),
        mes_mas_ajustado=str(serie["mes_mas_ajustado"]),
        valles=valles,
        caja_minima=str(serie.get("caja_minima", "0")),
        creado_por=usuario_id,
    )
    await nueva.insert()
    return nueva


async def version_vigente() -> ProyeccionVersion | None:
    return await ProyeccionVersion.find_one(
        ProyeccionVersion.vigente == True  # noqa: E712
    )


async def snapshot_version_aprobada(
    *,
    mes_aprobado: str,
    usuario_id: str,
    mes_inicio: tuple[int, int],
) -> ProyeccionVersion:
    """Corre la proyección base a horizonte completo y la congela. Se llama post-commit
    de la aprobación (best-effort: su fallo no revierte la aprobación)."""
    # import diferido: evita ciclo (service importa domain, no al revés)
    from app.proyeccion.service import proyectar_vigente, valles_vigente

    serie = await proyectar_vigente(
        escenario="base", mes_inicio=mes_inicio, horizonte_meses=None
    )
    vd = await valles_vigente(
        escenario="base", mes_inicio=mes_inicio, horizonte_meses=None
    )
    return await _persistir_version(
        serie=serie,
        valles=vd.get("valles", []),
        mes_aprobado=mes_aprobado,
        usuario_id=usuario_id,
    )


def diff_contra_vigente(
    serie_actual: dict,
    valles_actual: list[dict],
    anterior: ProyeccionVersion | None,
) -> dict:
    """Compara la proyección actual contra la última versión aprobada. Todo Decimal."""
    if anterior is None:
        return {"hay_anterior": False}
    piso_ant = Decimal(str(anterior.piso_caja))
    piso_act = Decimal(str(serie_actual["piso_caja"]))
    meses_valle_ant = {v.get("mes") for v in anterior.valles}
    meses_valle_act = {v.get("mes") for v in valles_actual}
    return {
        "hay_anterior": True,
        "version_anterior": anterior.version,
        "mes_aprobado_anterior": anterior.mes_aprobado,
        "piso": {
            "anterior": str(anterior.piso_caja),
            "actual": str(serie_actual["piso_caja"]),
            "delta": money_str(piso_act - piso_ant),
        },
        "mes_mas_ajustado": {
            "anterior": str(anterior.mes_mas_ajustado),
            "actual": str(serie_actual["mes_mas_ajustado"]),
        },
        "valles": {
            "anterior": len(anterior.valles),
            "actual": len(valles_actual),
            "nuevos": sorted(meses_valle_act - meses_valle_ant),
            "desaparecidos": sorted(meses_valle_ant - meses_valle_act),
        },
    }
