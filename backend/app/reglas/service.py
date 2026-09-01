# backend/app/reglas/service.py
"""C3 auto-clasificación (CR-S5, GO Kimi PLAN-I 9.3): reglas administrables.

MARCADO PARA AUDITORÍA KIMI (clasifica movimientos de dinero; gate I-PR1).

Decisiones fijadas en el gate del PLAN:
  - D1 (coherencia de tipos POR CONSTRUCCIÓN): `_validar_rubro_destino` exige
    rubro existente (404), activo (422) y con `tipo_flujo` == el de la regla (409)
    — en crear, editar Y en los dos puntos de activación (aprobar / PATCH
    activa:true — B-1 Kimi: el rubro pudo desactivarse entre la creación y la
    activación; el estado "regla activa → rubro inactivo" solo puede existir por
    desactivación POSTERIOR del rubro, nunca por decisión de activación).
  - D2 (guarda de inactivos): `elegir_regla` salta reglas cuyo rubro no esté en el
    set de activos — la fila cae a 'Por clasificar' (regla 7) y el llamador
    reporta (`reglas_con_rubro_inactivo`, fail-loud informativo patrón B-4).
    NO hay desactivación en cascada: si el rubro se reactiva, la regla vuelve a
    operar sola.
  - Precedencia DETERMINISTA: prioridad ascendente; empate → str(_id) (estable).
  - D4/B-2: `aplicar_pendientes` re-corre reglas SOLO sobre 'Por clasificar' de
    meses NO cerrados (regla 4) y SELLA cada doc con clasificada_por +
    clasificada_at + regla_id — rastro forense completo por documento (quién
    disparó el lote / cuándo / qué regla), sin evento agregado.
  - D5 (§1.9): las aprendidas nacen `activa=False` SIEMPRE (forzado en
    `proponer_regla_aprendida`) y solo se activan por `/aprobar` o PATCH
    activa:true (misma autoridad `reglas:gestionar`) — nunca una vía automática.
  - Auditoría FAIL-CLOSED estilo O1 (estándar C1/B-5): mutar → emitir →
    compensar si el emit falla → propagar.
"""

from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cierre.transito import RUBRO_TRANSITO, AsignadorTransito
from app.core.time import now_utc
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.regla_clasificacion import (
    OrigenRegla,
    ReglaClasificacion,
    coincide,
    normalizar_texto,
)
from app.domain.rubro import Rubro, TipoFlujo, es_rubro_clasificable
from app.domain.transaccion import Transaccion

RUBRO_POR_CLASIFICAR = "Por clasificar"


class ReglasError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


# ────────────────────────── matching (puro, testeable) ──────────────────────────


def elegir_regla(
    descripcion: str,
    reglas: list[ReglaClasificacion],
    rubros_activos: set[PydanticObjectId],
) -> ReglaClasificacion | None:
    """Primera regla que matchea por (prioridad asc, _id) — determinista.
    D2: una regla cuyo rubro no esté activo SE SALTA (el llamador reporta).
    El llamador ya particionó `reglas` por tipo_flujo (D1-ii)."""
    for regla in sorted(reglas, key=lambda r: (r.prioridad, str(r.id))):
        if regla.rubro_id not in rubros_activos:
            continue
        if coincide(regla.patron, descripcion):
            return regla
    return None


async def reglas_activas_por_tipo() -> dict[TipoFlujo, list[ReglaClasificacion]]:
    """Reglas activas particionadas por tipo_flujo (D1-ii: una regla de ingreso
    jamás se evalúa contra un egreso)."""
    out: dict[TipoFlujo, list[ReglaClasificacion]] = {
        TipoFlujo.EGRESO: [],
        TipoFlujo.INGRESO: [],
    }
    async for regla in ReglaClasificacion.find(ReglaClasificacion.activa == True):  # noqa: E712
        out[regla.tipo_flujo].append(regla)
    return out


async def rubros_activos_ids() -> set[PydanticObjectId]:
    ids: set[PydanticObjectId] = set()
    async for r in Rubro.find(Rubro.activo == True):  # noqa: E712
        ids.add(r.id)
    return ids


# ────────────────────────────── CRUD ──────────────────────────────


async def _obtener(regla_id: str) -> ReglaClasificacion:
    try:
        rid = PydanticObjectId(regla_id)
    except Exception:
        raise ReglasError("regla_id inválido", 422) from None
    regla = await ReglaClasificacion.get(rid)
    if regla is None:
        raise ReglasError("la regla no existe", 404)
    return regla


async def _validar_rubro_destino(
    rubro_id: PydanticObjectId, tipo_flujo: TipoFlujo
) -> Rubro:
    """D1 + B-1: rubro existente (404), ACTIVO (422) y de tipo coherente (409).
    Se invoca al crear, al editar el destino y en TODA activación."""
    rubro = await Rubro.get(rubro_id)
    if rubro is None:
        raise ReglasError("el rubro destino no existe", 404)
    if not rubro.activo:
        raise ReglasError(f"el rubro '{rubro.nombre}' está inactivo (D1)", 422)
    if rubro.tipo_flujo is not tipo_flujo:
        raise ReglasError(
            f"el rubro '{rubro.nombre}' es {rubro.tipo_flujo.value}, incoherente "
            f"con una regla de {tipo_flujo.value} (D1)",
            409,
        )
    if not es_rubro_clasificable(rubro):
        raise ReglasError(
            f"el rubro '{rubro.nombre}' es de sistema y no admite reglas de "
            "clasificación (P0-1)",
            422,
        )
    return rubro


async def _patron_activo_duplicado(
    patron: str, tipo_flujo: TipoFlujo, excepto: PydanticObjectId | None = None
) -> bool:
    filtros = [
        ReglaClasificacion.patron_normalizado == normalizar_texto(patron),
        ReglaClasificacion.tipo_flujo == tipo_flujo,
        ReglaClasificacion.activa == True,  # noqa: E712
    ]
    existente = await ReglaClasificacion.find(*filtros).first_or_none()
    return existente is not None and (excepto is None or existente.id != excepto)


async def listar_reglas(
    *, activa: bool | None = None, tipo_flujo: TipoFlujo | None = None
) -> list[ReglaClasificacion]:
    filtros = []
    if activa is not None:
        filtros.append(ReglaClasificacion.activa == activa)
    if tipo_flujo is not None:
        filtros.append(ReglaClasificacion.tipo_flujo == tipo_flujo)
    return (
        await ReglaClasificacion.find(*filtros)
        .sort(+ReglaClasificacion.prioridad)
        .to_list()
    )


async def crear_regla(
    *,
    patron: str,
    rubro_id: str,
    tipo_flujo: TipoFlujo,
    prioridad: int,
    usuario_id: str,
) -> ReglaClasificacion:
    try:
        rid = PydanticObjectId(rubro_id)
    except Exception:
        raise ReglasError("rubro_id inválido", 422) from None
    rubro = await _validar_rubro_destino(rid, tipo_flujo)
    if await _patron_activo_duplicado(patron, tipo_flujo):
        raise ReglasError(
            f"ya existe una regla ACTIVA con el patrón '{patron}' para "
            f"{tipo_flujo.value} (regla 7: ambigüedad)",
            409,
        )
    regla = ReglaClasificacion(
        patron=patron,
        rubro_id=rid,
        tipo_flujo=tipo_flujo,
        prioridad=prioridad,
        origen=OrigenRegla.MANUAL,
        creada_por=usuario_id,
    )
    try:
        await regla.insert()
    except DuplicateKeyError:
        raise ReglasError(
            f"ya existe una regla ACTIVA con el patrón '{patron}'", 409
        ) from None
    try:
        await emit_audit(
            AuditEvento.regla_creada,
            entidad="regla_clasificacion",
            entidad_id=str(regla.id),
            actor_id=usuario_id,
            metadata={
                "patron": patron,
                "tipo_flujo": tipo_flujo.value,
                "rubro": rubro.nombre,
                "prioridad": prioridad,
                "origen": regla.origen.value,
            },
        )
    except Exception:
        await regla.delete()  # B-5/O1: sin rastro no hay regla
        raise
    return regla


async def proponer_regla_aprendida(
    *,
    patron: str,
    rubro_id: PydanticObjectId,
    tipo_flujo: TipoFlujo,
    usuario_id: str,
    prioridad: int = 100,
) -> ReglaClasificacion:
    """D5 (§1.9): la ÚNICA vía de creación de aprendidas — fuerza activa=False
    (nunca auto-activada); la activa el Financiero por /aprobar."""
    rubro = await _validar_rubro_destino(rubro_id, tipo_flujo)
    if await _patron_activo_duplicado(patron, tipo_flujo):
        raise ReglasError(f"ya existe una regla ACTIVA con el patrón '{patron}'", 409)
    regla = ReglaClasificacion(
        patron=patron,
        rubro_id=rubro_id,
        tipo_flujo=tipo_flujo,
        prioridad=prioridad,
        origen=OrigenRegla.APRENDIDA,
        activa=False,  # §1.9: NUNCA auto-activada
        creada_por=usuario_id,
    )
    await regla.insert()
    try:
        await emit_audit(
            AuditEvento.regla_creada,
            entidad="regla_clasificacion",
            entidad_id=str(regla.id),
            actor_id=usuario_id,
            metadata={
                "patron": patron,
                "tipo_flujo": tipo_flujo.value,
                "rubro": rubro.nombre,
                "origen": "aprendida",
                "activa": False,
            },
        )
    except Exception:
        await regla.delete()
        raise
    return regla


async def editar_regla(
    *,
    regla_id: str,
    usuario_id: str,
    patron: str | None = None,
    prioridad: int | None = None,
    rubro_id: str | None = None,
    activa: bool | None = None,
) -> ReglaClasificacion:
    regla = await _obtener(regla_id)
    cambios: dict[str, dict] = {}
    previos: dict[str, object] = {}

    if activa is not None:
        if activa is False:
            raise ReglasError(
                "la baja va por POST /reglas-clasificacion/{id}/desactivar", 422
            )
        if not regla.activa:
            # B-1 Kimi: la ACTIVACIÓN revalida el destino (pudo desactivarse
            # el rubro entre la creación y este momento).
            destino = (
                PydanticObjectId(rubro_id) if rubro_id is not None else regla.rubro_id
            )
            await _validar_rubro_destino_para_activar(destino, regla.tipo_flujo)
            if await _patron_activo_duplicado(
                patron if patron is not None else regla.patron,
                regla.tipo_flujo,
                excepto=regla.id,
            ):
                raise ReglasError("otra regla ACTIVA ya usa ese patrón", 409)
            previos["activa"] = regla.activa
            cambios["activa"] = {"anterior": False, "nuevo": True}
            regla.activa = True

    if rubro_id is not None:
        try:
            rid = PydanticObjectId(rubro_id)
        except Exception:
            raise ReglasError("rubro_id inválido", 422) from None
        if rid != regla.rubro_id:
            await _validar_rubro_destino(rid, regla.tipo_flujo)
            previos["rubro_id"] = regla.rubro_id
            cambios["rubro_id"] = {"anterior": str(regla.rubro_id), "nuevo": str(rid)}
            regla.rubro_id = rid

    if patron is not None and patron != regla.patron:
        if regla.activa and await _patron_activo_duplicado(
            patron, regla.tipo_flujo, excepto=regla.id
        ):
            raise ReglasError("otra regla ACTIVA ya usa ese patrón", 409)
        previos["patron"] = regla.patron
        cambios["patron"] = {"anterior": regla.patron, "nuevo": patron}
        regla.patron = patron

    if prioridad is not None and prioridad != regla.prioridad:
        previos["prioridad"] = regla.prioridad
        cambios["prioridad"] = {"anterior": regla.prioridad, "nuevo": prioridad}
        regla.prioridad = prioridad

    if not cambios:
        raise ReglasError("nada que editar (ningún campo cambia)", 422)

    try:
        await regla.save()
    except DuplicateKeyError:
        raise ReglasError("otra regla ACTIVA ya usa ese patrón", 409) from None

    try:
        await emit_audit(
            AuditEvento.regla_editada,
            entidad="regla_clasificacion",
            entidad_id=str(regla.id),
            actor_id=usuario_id,
            metadata={"cambios": cambios},
        )
    except Exception:
        for campo, valor in previos.items():
            setattr(regla, campo, valor)
        await regla.save()
        raise
    return regla


async def _validar_rubro_destino_para_activar(
    rubro_id: PydanticObjectId, tipo_flujo: TipoFlujo
) -> Rubro:
    """B-1: en activación, rubro inactivo/incoherente es 409 (decisión explícita
    de activar hacia un destino inválido, no un dato mal formado)."""
    rubro = await Rubro.get(rubro_id)
    if rubro is None:
        raise ReglasError("el rubro destino no existe", 404)
    if not rubro.activo:
        raise ReglasError(
            f"no se puede activar: el rubro '{rubro.nombre}' está inactivo (B-1)",
            409,
        )
    if rubro.tipo_flujo is not tipo_flujo:
        raise ReglasError(
            f"no se puede activar: el rubro '{rubro.nombre}' es "
            f"{rubro.tipo_flujo.value} (B-1/D1)",
            409,
        )
    return rubro


async def desactivar_regla(*, regla_id: str, usuario_id: str) -> ReglaClasificacion:
    regla = await _obtener(regla_id)
    if not regla.activa:
        raise ReglasError("la regla ya está inactiva", 409)
    regla.activa = False
    await regla.save()
    try:
        await emit_audit(
            AuditEvento.regla_desactivada,
            entidad="regla_clasificacion",
            entidad_id=str(regla.id),
            actor_id=usuario_id,
            metadata={"patron": regla.patron},
        )
    except Exception:
        regla.activa = True
        await regla.save()
        raise
    return regla


async def aprobar_regla(*, regla_id: str, usuario_id: str) -> ReglaClasificacion:
    """§1.9: activa una regla APRENDIDA propuesta. B-1: revalida el destino."""
    regla = await _obtener(regla_id)
    if regla.origen is not OrigenRegla.APRENDIDA:
        raise ReglasError("solo las reglas aprendidas pasan por aprobación", 409)
    if regla.activa:
        raise ReglasError("la regla ya está activa", 409)
    await _validar_rubro_destino_para_activar(regla.rubro_id, regla.tipo_flujo)
    if await _patron_activo_duplicado(regla.patron, regla.tipo_flujo, excepto=regla.id):
        raise ReglasError("otra regla ACTIVA ya usa ese patrón", 409)

    regla.activa = True
    await regla.save()
    try:
        await emit_audit(
            AuditEvento.regla_editada,
            entidad="regla_clasificacion",
            entidad_id=str(regla.id),
            actor_id=usuario_id,
            metadata={
                "cambios": {"activa": {"anterior": False, "nuevo": True}},
                "via": "aprobacion",
            },
        )
    except Exception:
        regla.activa = False
        await regla.save()
        raise
    return regla


# ────────────────────── aplicar-pendientes (D4 + B-2) ──────────────────────


async def aplicar_pendientes(*, usuario_id: str) -> dict:
    """Re-corre las reglas SOLO sobre 'Por clasificar' de meses NO cerrados
    (regla 4). Idempotente: lo ya clasificado no se toca. B-2: cada doc
    reclasificado queda SELLADO con clasificada_por/at + regla_id."""
    pc = await Rubro.find_one(Rubro.nombre == RUBRO_POR_CLASIFICAR)
    if pc is None:
        raise ReglasError(
            "falta el rubro de sistema 'Por clasificar' (correr semillas)", 500
        )
    mes_por_id = {
        mc.id: mc.mes
        async for mc in MesControl.find(MesControl.estado != EstadoMes.CERRADO)
    }
    meses_abiertos = list(mes_por_id.keys())
    por_tipo = await reglas_activas_por_tipo()
    activos = await rubros_activos_ids()

    # CR-WAVA-2: hook estado-dependiente (mismo criterio que la carga). Un depósito
    # Wava pendiente con remanente vivo se reclasifica al rubro tránsito ANTES de las
    # reglas; fail-safe si el rubro no existe. El asignador descuenta en batch.
    rubro_transito = await Rubro.find_one(Rubro.nombre == RUBRO_TRANSITO)
    asignador = AsignadorTransito()

    clasificadas = 0
    sin_match = 0
    ahora = now_utc()
    async for tx in Transaccion.find(
        Transaccion.rubro_id == pc.id,
        {"mes_id": {"$in": meses_abiertos}},
    ):
        if rubro_transito is not None and await asignador.asigna(
            descripcion=tx.descripcion,
            mes=mes_por_id[tx.mes_id],
            tipo_flujo=tx.tipo_flujo,
            valor=tx.valor,
        ):
            tx.rubro_id = rubro_transito.id
            tx.regla_id = None  # sello de sistema, no de regla
            tx.clasificada_por = usuario_id  # B-2: quién disparó el lote
            tx.clasificada_at = ahora  # B-2: cuándo
            await tx.save()
            clasificadas += 1
            continue
        regla = elegir_regla(tx.descripcion, por_tipo[tx.tipo_flujo], activos)
        if regla is None:
            sin_match += 1
            continue
        tx.rubro_id = regla.rubro_id
        tx.regla_id = regla.id
        tx.clasificada_por = usuario_id  # B-2: quién disparó el lote
        tx.clasificada_at = ahora  # B-2: cuándo
        await tx.save()
        clasificadas += 1

    return {
        "clasificadas": clasificadas,
        "sin_match": sin_match,
        # B-1 I-PR1 (simetría D2 con la carga): distinguir "no hay regla" de
        # "hay regla pero su rubro está inactivo" (fail-loud informativo).
        "reglas_con_rubro_inactivo": sorted(
            r.patron
            for reglas in por_tipo.values()
            for r in reglas
            if r.rubro_id not in activos
        ),
    }


# ───────────────── RV-V8/V9 · bandeja "Por clasificar" ─────────────────────
#
# Lista los movimientos con rubro 'Por clasificar' en meses NO cerrados,
# agrupados por (descripción normalizada, tipo_flujo) — misma normalización
# que usa el clasificador (patron_normalizado) para que la agrupación cuadre
# con lo que va a matchear una regla creada desde aquí. Cada grupo trae:
#   - descripcion_muestra: la 1ª descripción del grupo (frontend la usa como
#     `patron` sugerido al pre-poblar el form)
#   - tipo_flujo: 'egreso' | 'ingreso'
#   - muestras: cuántas transacciones caen bajo la misma normalización
#   - ejemplos: hasta 3 descripciones distintas del grupo (para que el CEO
#     vea la variedad y no adivine el patrón desde una sola muestra)
#
# NO paginamos: si la bandeja tiene miles de grupos, el problema real es
# semilla de reglas, no UX de scroll. Kimi B-2 similar en aplicar-pendientes.


async def listar_por_clasificar() -> list[dict]:
    pc = await Rubro.find_one(Rubro.nombre == RUBRO_POR_CLASIFICAR)
    if pc is None:
        return []
    meses_abiertos = [
        mc.id
        async for mc in MesControl.find(MesControl.estado != EstadoMes.CERRADO)
    ]
    if not meses_abiertos:
        return []

    grupos: dict[tuple[str, str], dict] = {}
    async for tx in Transaccion.find(
        Transaccion.rubro_id == pc.id,
        {"mes_id": {"$in": meses_abiertos}},
    ):
        tipo = tx.tipo_flujo.value if hasattr(tx.tipo_flujo, "value") else str(tx.tipo_flujo)
        # Agrupamiento por PRIMERA PALABRA de la descripción normalizada — así
        # 40 pagos de "UBER 12345", "UBER 67890"… caen en UN grupo con clave
        # "uber", y el CEO ve la señal ("40 UBER sin clasificar") en vez de
        # 40 líneas. Fallback: normalización completa si no hay palabras.
        norm = normalizar_texto(tx.descripcion)
        primera_palabra = norm.split(maxsplit=1)[0] if norm.split() else norm
        clave = (primera_palabra, tipo)
        g = grupos.get(clave)
        if g is None:
            g = {
                "descripcion_muestra": tx.descripcion,
                "tipo_flujo": tipo,
                "muestras": 0,
                "ejemplos": [],
            }
            grupos[clave] = g
        g["muestras"] += 1
        # Ejemplos: hasta 3 descripciones DISTINTAS (evita ruido por N idénticas).
        if len(g["ejemplos"]) < 3 and tx.descripcion not in g["ejemplos"]:
            g["ejemplos"].append(tx.descripcion)

    # Orden estable: los grupos más grandes primero (más impacto al crear regla).
    return sorted(
        grupos.values(),
        key=lambda g: (-g["muestras"], g["descripcion_muestra"]),
    )
