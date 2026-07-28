# backend/app/loantape/service.py
"""Carga del LoanTape semanal de SISMO-V3 + lectura del aging (mora por tramo).

Contrato: docs/CONTRATO-SISMO-V3-LOANTAPE.md. `parse_fila_loantape` transforma una fila
CRUDA (dict de strings del CSV/Excel) a los tipos del dominio; fila ambigua = error
reportado, JAMÁS adivinado (regla 7). `cargar_loantape` hace upsert por
(credito_id, fecha_corte) — idempotente, pisa el corte — y emite `loantape.cargado`
(fail-closed). `obtener_aging` deriva la mora por tramo del corte MÁS RECIENTE.
"""

from decimal import Decimal, InvalidOperation

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.domain.loantape import EstadoCredito, LoanTapeCredito
from app.loantape.aging import aging_por_tramo

_REQ_TEXTO = ("credito_id", "fecha_corte", "modelo", "fecha_desembolso", "estado")
_REQ_MONEY = ("monto_financiado", "cuota_semanal", "saldo_en_mora", "saldo_pendiente")
_REQ_INT = ("plazo_semanas", "cuotas_pagadas", "cuotas_vencidas", "dias_mora")


class LoanTapeError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


def _money(v: str, campo: str, cid: str) -> Decimal:
    try:
        return Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        raise LoanTapeError(
            f"crédito {cid}: {campo} no es un decimal válido: {v!r}"
        ) from None


def _int(v: str, campo: str, cid: str) -> int:
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        raise LoanTapeError(
            f"crédito {cid}: {campo} no es un entero válido: {v!r}"
        ) from None


def parse_fila_loantape(raw: dict) -> dict:
    """Valida y coacciona UNA fila cruda al kwargs de `LoanTapeCredito`. No adivina:
    REQ vacío o mal tipado → LoanTapeError con el crédito y el campo señalados."""
    cid = str(raw.get("credito_id", "") or "").strip()
    for campo in _REQ_TEXTO:
        if not str(raw.get(campo, "") or "").strip():
            falta = campo
            raise LoanTapeError(
                f"crédito {cid or '?'}: falta el campo requerido {falta}"
            )

    estado_raw = str(raw["estado"]).strip()
    if estado_raw not in EstadoCredito._value2member_map_:
        raise LoanTapeError(f"crédito {cid}: estado inválido: {estado_raw!r}")

    def _opc(campo: str) -> str | None:
        v = str(raw.get(campo, "") or "").strip()
        return v or None

    return {
        "credito_id": cid,
        "fecha_corte": str(raw["fecha_corte"]).strip(),
        "modelo": str(raw["modelo"]).strip(),
        "fecha_desembolso": str(raw["fecha_desembolso"]).strip(),
        "monto_financiado": _money(raw["monto_financiado"], "monto_financiado", cid),
        "plazo_semanas": _int(raw["plazo_semanas"], "plazo_semanas", cid),
        "cuota_semanal": _money(raw["cuota_semanal"], "cuota_semanal", cid),
        "cuotas_pagadas": _int(raw["cuotas_pagadas"], "cuotas_pagadas", cid),
        "cuotas_vencidas": _int(raw["cuotas_vencidas"], "cuotas_vencidas", cid),
        "dias_mora": _int(raw["dias_mora"], "dias_mora", cid),
        "saldo_en_mora": _money(raw["saldo_en_mora"], "saldo_en_mora", cid),
        "saldo_pendiente": _money(raw["saldo_pendiente"], "saldo_pendiente", cid),
        "estado": estado_raw,
        "cliente_id": _opc("cliente_id"),
        "fecha_ultimo_pago": _opc("fecha_ultimo_pago"),
    }


async def cargar_loantape(filas: list[dict], usuario_id: str) -> int:
    """Parsea + upsert por (credito_id, fecha_corte). Idempotente: recargar un corte
    pisa, no duplica. Valida TODAS las filas antes de escribir (todo-o-nada en el parse:
    una fila ambigua aborta la carga entera). Emite `loantape.cargado`."""
    parsed = [parse_fila_loantape(f) for f in filas]  # falla-rápido si alguna es mala
    cortes: set[str] = set()
    for p in parsed:
        cortes.add(p["fecha_corte"])
        existente = await LoanTapeCredito.find_one(
            LoanTapeCredito.credito_id == p["credito_id"],
            LoanTapeCredito.fecha_corte == p["fecha_corte"],
        )
        if existente is None:
            await LoanTapeCredito(**p).insert()
        else:
            for k, v in p.items():
                setattr(existente, k, v)
            await existente.save()
    await emit_audit(
        AuditEvento.loantape_cargado,
        entidad="loantape",
        entidad_id=",".join(sorted(cortes)) or "-",
        actor_id=usuario_id,
        metadata={"creditos": len(parsed), "cortes": sorted(cortes)},
    )
    return len(parsed)


async def _ultimo_corte() -> str | None:
    doc = (
        await LoanTapeCredito.find_all()
        .sort(-LoanTapeCredito.fecha_corte)
        .limit(1)
        .to_list()
    )
    return doc[0].fecha_corte if doc else None


async def obtener_aging(fecha_corte: str | None = None) -> dict:
    """Aging (mora por tramo) del corte indicado; por defecto el MÁS RECIENTE. Devuelve
    {fecha_corte, tramos:[{tramo, etiqueta, n_creditos, saldo_en_mora}]}."""
    corte = fecha_corte or await _ultimo_corte()
    if corte is None:
        return {"fecha_corte": None, "tramos": aging_por_tramo([])}
    creditos = await LoanTapeCredito.find(
        LoanTapeCredito.fecha_corte == corte
    ).to_list()
    items = [
        {"dias_mora": c.dias_mora, "saldo_en_mora": c.saldo_en_mora} for c in creditos
    ]
    return {"fecha_corte": corte, "tramos": aging_por_tramo(items)}
