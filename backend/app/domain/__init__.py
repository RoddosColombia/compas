# backend/app/domain/__init__.py
"""Modelos de dominio base (Beanie Documents) + registro para init_beanie.

`DOMAIN_DOCUMENTS` es la lista EXPLÍCITA de Documents que se registran en Beanie
(Kimi M-04). `AuditLog`, `User` y `RefreshSession` NO están aquí: sus escrituras van
por repositorios con Motor crudo/conexión dedicada (decisión de la Sesión 2), no por
el ODM general.
"""

from app.domain.carga import CargaBancaria
from app.domain.configuracion import Configuracion
from app.domain.idempotency import IdempotencyKey
from app.domain.mes_control import MesControl
from app.domain.presupuesto import PresupuestoLinea
from app.domain.regla_clasificacion import ReglaClasificacion
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion

DOMAIN_DOCUMENTS: list[type] = [
    Rubro,
    MesControl,
    Configuracion,
    Transaccion,
    CargaBancaria,
    IdempotencyKey,
    PresupuestoLinea,
    ReglaClasificacion,
]

__all__ = [
    "Rubro",
    "MesControl",
    "Configuracion",
    "Transaccion",
    "CargaBancaria",
    "IdempotencyKey",
    "PresupuestoLinea",
    "ReglaClasificacion",
    "DOMAIN_DOCUMENTS",
]
