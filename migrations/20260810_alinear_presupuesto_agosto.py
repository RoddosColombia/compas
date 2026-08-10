#!/usr/bin/env python
"""Migración idempotente: alinea el presupuesto de AGOSTO-2026 al Excel del CEO
("Flujo de pagos deudas.xlsx", hoja Presupuesto, col 2026-08) — decisión CEO 2026-08-10.

Qué hace (y qué NO):
1. Crea, si faltan, 4 rubros que existen en el Excel y no en PROD — vía servicio
   (`crear_rubro`, evento `rubro.creado`, fail-closed O1):
     · Cuotas iniciales            (0120, ingresos_operativos/ingreso)  [decisión CEO: partir el real]
     · Seguro créditos activos     (2160, operacion/egreso)
     · Rodante – Financiación a clientes (4070, deudas_obligaciones/egreso)
     · Contabilidad                (5080, otros/egreso)
2. Lleva `monto_definido` de cada línea de agosto-2026 al valor del Excel:
     · línea vigente existente → `acotar_linea()` (Ajuste append-only + evento + FIX-G1:
       comentario obligatorio por estar en ejecución); skip si ya está alineada;
     · rubro sin línea en el ciclo → crea la línea (version=1, sugerido 0,
       historia_incompleta=True, definido=None) y luego `acotar_linea()` — así TODO
       cambio de monto queda con el MISMO rastro de auditoría.
3. Contingencia (2150) → definido 0 (decisión CEO: se desglosó todo; no debe sumar) e
   intento de baja lógica vía servicio; si tiene referencias, queda activa en 0 y se reporta.

NO toca: julio ni ningún mes cerrado (regla 4), la proyección, el motor, transacciones,
el rubro "Aportes de capital" (no está en el Excel; queda como está).

Idempotente: rubros por índice único (grupo, nombre); líneas por índice vigente único;
montos por skip-si-igual. Re-correr = 0 cambios.

TOTAL definido esperado tras la corrida: $255.109.500 (Contingencia en 0 no suma).

Uso (Windows: PYTHONUTF8=1):
    MONGODB_URI_COMPAS="<uri>" MONGODB_URI_AUDIT="<uri>" \\
        python migrations/20260810_alinear_presupuesto_agosto.py [db=compas]
"""

from __future__ import annotations

import asyncio
import os
import sys
from decimal import Decimal

sys.path.insert(0, "backend")

from app.audit.service import configure_audit  # noqa: E402
from app.db import mongo  # noqa: E402
from app.domain.mes_control import MesControl  # noqa: E402
from app.domain.presupuesto import ModoCalculo, PresupuestoLinea  # noqa: E402
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo  # noqa: E402
from app.presupuesto.service import acotar_linea  # noqa: E402
from app.rubros.service import RubrosError, crear_rubro, desactivar_rubro  # noqa: E402

MES = "2026-08-01"
COMENTARIO = (
    "Alineación al Excel 'Flujo de pagos deudas' (hoja Presupuesto, ago-2026) — "
    "decisión CEO 2026-08-10 (sesión 6 puntos pre-FABS)"
)

# Rubros del Excel ausentes en PROD: (grupo, nombre, tipo_flujo, codigo)
RUBROS_NUEVOS: list[tuple[RubroGrupo, str, TipoFlujo, str]] = [
    (RubroGrupo.INGRESOS_OPERATIVOS, "Cuotas iniciales", TipoFlujo.INGRESO, "0120"),
    (RubroGrupo.OPERACION, "Seguro créditos activos", TipoFlujo.EGRESO, "2160"),
    (
        RubroGrupo.DEUDAS_OBLIGACIONES,
        "Rodante – Financiación a clientes",
        TipoFlujo.EGRESO,
        "4070",
    ),
    (RubroGrupo.OTROS, "Contabilidad", TipoFlujo.EGRESO, "5080"),
]

# Objetivo del Excel para agosto-2026: (grupo, nombre, definido).
# El match a PROD es por (grupo, nombre) — hay rubros sin código en la taxonomía.
OBJETIVO: list[tuple[RubroGrupo, str, Decimal]] = [
    (RubroGrupo.COSTO_PRODUCTO, "Producto", Decimal("0")),
    (RubroGrupo.COSTO_PRODUCTO, "SOAT/Matrículas", Decimal("38000000")),
    (RubroGrupo.COSTO_PRODUCTO, "Combustible motos", Decimal("150000")),
    (RubroGrupo.COSTO_PRODUCTO, "Seguros (Hunter)", Decimal("9000000")),
    (RubroGrupo.OPERACION, "Arriendos", Decimal("8370127")),
    (RubroGrupo.OPERACION, "Tecnología y software", Decimal("3500000")),
    (RubroGrupo.OPERACION, "Mobiliario/planta/equipo", Decimal("760000")),
    (RubroGrupo.OPERACION, "Servicios públicos y telecom", Decimal("1210000")),
    (RubroGrupo.OPERACION, "Mercado y aseo", Decimal("550000")),
    (RubroGrupo.OPERACION, "Cafetería", Decimal("350000")),
    (
        RubroGrupo.OPERACION,
        "Transporte/peajes/combustible/parqueo",
        Decimal("1750000"),
    ),
    (RubroGrupo.OPERACION, "Papelería", Decimal("250000")),
    (RubroGrupo.OPERACION, "Marketing y publicidad", Decimal("2000000")),
    (RubroGrupo.OPERACION, "Gastos de representación", Decimal("1500000")),
    (RubroGrupo.OPERACION, "Viajes corporativos", Decimal("1600000")),
    (RubroGrupo.OPERACION, "Grúas y traslados", Decimal("150000")),
    (RubroGrupo.OPERACION, "Freelance", Decimal("350000")),
    (RubroGrupo.OPERACION, "Comisiones externas", Decimal("350000")),
    (RubroGrupo.OPERACION, "Seguro créditos activos", Decimal("6450000")),
    (RubroGrupo.OPERACION, "Renting", Decimal("8600000")),
    (RubroGrupo.OPERACION, "Contingencia", Decimal("0")),  # decisión CEO: no suma
    (RubroGrupo.NOMINA, "Sueldos empleados", Decimal("13726236")),
    (RubroGrupo.NOMINA, "Sueldos directivos", Decimal("39984000")),
    (RubroGrupo.NOMINA, "Bonificaciones", Decimal("34650000")),
    (RubroGrupo.NOMINA, "Beneficios Heads", Decimal("0")),
    (RubroGrupo.NOMINA, "Dotación empleados", Decimal("0")),
    (RubroGrupo.NOMINA, "Planillas nuevas", Decimal("8448968")),
    (RubroGrupo.NOMINA, "Planillas anteriores", Decimal("0")),
    (RubroGrupo.NOMINA, "Parafiscales", Decimal("6605169")),
    (RubroGrupo.DEUDAS_OBLIGACIONES, "Préstamos", Decimal("21000000")),
    (RubroGrupo.DEUDAS_OBLIGACIONES, "Deudas tarjetas de crédito", Decimal("0")),
    (RubroGrupo.DEUDAS_OBLIGACIONES, "Garantía cupo", Decimal("14000000")),
    (RubroGrupo.DEUDAS_OBLIGACIONES, "Deudas impuestos", Decimal("1000000")),
    (
        RubroGrupo.DEUDAS_OBLIGACIONES,
        "Deudas proveedores anteriores",
        Decimal("20000000"),
    ),
    (
        RubroGrupo.DEUDAS_OBLIGACIONES,
        "Rodante – Financiación a clientes",
        Decimal("3000000"),
    ),
    (RubroGrupo.OTROS, "Otros gastos", Decimal("1000000")),
    (RubroGrupo.OTROS, "Gastos notariales", Decimal("120000")),
    (RubroGrupo.OTROS, "Asuntos legales", Decimal("750000")),
    (RubroGrupo.OTROS, "Gastos bancarios", Decimal("85000")),
    (RubroGrupo.OTROS, "Gastos financieros", Decimal("0")),
    (RubroGrupo.OTROS, "Impuestos", Decimal("3000000")),
    (RubroGrupo.OTROS, "Contabilidad", Decimal("2100000")),
    (RubroGrupo.OTROS, "Por clasificar", Decimal("750000")),
]

TOTAL_ESPERADO = Decimal("255109500")


async def _usuario_andres() -> str:
    doc = await mongo_db["users"].find_one({"email": "andres@roddos.com"})
    if not doc:
        sys.exit("ERROR: no existe el usuario andres@roddos.com en la base")
    return str(doc["_id"])


mongo_db = None  # se fija en _run (para _usuario_andres)


async def _run(uri: str, uri_audit: str, db_name: str) -> None:
    global mongo_db
    client = mongo.create_client(uri)
    await mongo.init_beanie_for(client, db_name)
    mongo_db = client[db_name]

    audit_client = mongo.create_client(uri_audit)
    configure_audit(audit_client, db_name)

    usuario_id = await _usuario_andres()

    mc = await MesControl.find_one(MesControl.mes == MES)
    if mc is None:
        sys.exit(f"ERROR: no existe el mes de control {MES}")
    print(f"[mes] {MES} estado={mc.estado.value} (julio y anteriores: NO se tocan)")

    # ── 1. Rubros nuevos (idempotente por grupo+nombre; evento rubro.creado) ──
    for grupo, nombre, flujo, codigo in RUBROS_NUEVOS:
        existente = await Rubro.find_one(Rubro.grupo == grupo, Rubro.nombre == nombre)
        if existente is not None:
            print(f"[rubro] ya existe: {grupo.value}/{nombre} (skip)")
            continue
        r = await crear_rubro(
            grupo=grupo,
            nombre=nombre,
            tipo_flujo=flujo,
            usuario_id=usuario_id,
            codigo=codigo,
        )
        print(f"[rubro] CREADO {codigo} {grupo.value}/{nombre} (id={r.id})")

    # ── 2. Alinear montos definidos de agosto ──
    rubros = {(r.grupo, r.nombre): r async for r in Rubro.find_all()}
    cambios = 0
    creadas = 0
    for grupo, nombre, objetivo in OBJETIVO:
        r = rubros.get((grupo, nombre))
        if r is None:
            print(f"[FALTA] rubro no hallado: {grupo.value}/{nombre} — REVISAR")
            continue
        ln = await PresupuestoLinea.find_one(
            PresupuestoLinea.mes_id == mc.id,
            PresupuestoLinea.rubro_id == r.id,
            PresupuestoLinea.vigente == True,  # noqa: E712
        )
        if ln is None:
            # Rubro sin línea en el ciclo de agosto: crearla en cero y acotar por el
            # servicio para que el cambio de monto tenga el rastro estándar.
            ln = PresupuestoLinea(
                mes_id=mc.id,
                rubro_id=r.id,
                version=1,
                monto_sugerido=Decimal("0"),
                prom_3m=Decimal("0"),
                tendencia_mes=Decimal("0"),
                crec_pct=Decimal("0"),
                compromisos_programados=Decimal("0"),
                monto_definido=None,
                creada_por=usuario_id,
                historia_incompleta=True,
                modo_calculo=ModoCalculo.HISTORICO,
                vigente=True,
            )
            await ln.insert()
            creadas += 1
            print(f"[línea] creada para {nombre} (sin línea en el ciclo)")
        actual = ln.monto_definido
        if actual is not None and Decimal(str(actual)) == objetivo:
            continue  # ya alineada
        await acotar_linea(
            mes=MES,
            rubro_id=str(r.id),
            monto_definido=objetivo,
            comentario=COMENTARIO,
            usuario_id=usuario_id,
        )
        cambios += 1
        antes = f"{Decimal(str(actual)):,.0f}" if actual is not None else "—"
        print(f"[acotar] {nombre}: {antes} → {objetivo:,.0f}")

    # ── 3. Contingencia: baja lógica si no tiene referencias ──
    conting = rubros.get((RubroGrupo.OPERACION, "Contingencia"))
    if conting is not None and getattr(conting, "activo", True):
        try:
            await desactivar_rubro(rubro_id=str(conting.id), usuario_id=usuario_id)
            print("[rubro] Contingencia desactivada (baja lógica, evento emitido)")
        except RubrosError as e:
            print(f"[rubro] Contingencia queda ACTIVA en $0 ({e})")

    # ── Verificación final ──
    total = Decimal("0")
    async for ln in PresupuestoLinea.find(
        PresupuestoLinea.mes_id == mc.id,
        PresupuestoLinea.vigente == True,  # noqa: E712
    ):
        if ln.monto_definido is not None:
            total += Decimal(str(ln.monto_definido))
    print(
        f"[fin] cambios={cambios} líneas_creadas={creadas} | "
        f"TOTAL definido agosto = {total:,.0f} (esperado {TOTAL_ESPERADO:,.0f})"
    )
    if total != TOTAL_ESPERADO:
        print("[AVISO] el total NO coincide con el esperado — revisar diferencias")
    client.close()
    audit_client.close()


def main() -> None:
    uri = os.environ.get("MONGODB_URI_COMPAS") or os.environ.get("MONGODB_URI")
    uri_audit = os.environ.get("MONGODB_URI_AUDIT")
    if not uri or not uri_audit:
        sys.exit(
            "ERROR: faltan MONGODB_URI_COMPAS y/o MONGODB_URI_AUDIT en el entorno "
            "(nunca por argv). Uso: MONGODB_URI_COMPAS=... MONGODB_URI_AUDIT=... "
            "python migrations/20260810_alinear_presupuesto_agosto.py [db=compas]"
        )
    db_name = sys.argv[1] if len(sys.argv) > 1 else "compas"
    asyncio.run(_run(uri, uri_audit, db_name))


if __name__ == "__main__":
    main()
