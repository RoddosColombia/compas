# backend/app/domain/modelo_moto.py
"""ModeloMoto (COCK-02, CR-COCK) — catálogo ADMINISTRABLE de modelos de moto para el
motor de proyección (C7). Paralelo EXACTO de C1 (Rubro): alta/edición desde la app,
baja LÓGICA (un modelo con proyección no se borra), único por nombre, rubros de
sistema inmutables. Requisito CEO 2026-07-22: agregar modelos nuevos sin tocar código.

Cada modelo trae su estructura de cobro (costo Auteco · precio venta+IVA · cuota
inicial · cuota semanal · plazo · matrícula) + participación en el mix. El motor
(`proyeccion/motor.py`) consume el catálogo VIGENTE (activos) para proyectar ventas y
recaudo. Todo monto es Decimal/Money (regla 1); `participacion_mix` es fracción 0..1.
"""

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import IndexModel

from app.core.money import Money

MODELOS_MOTO_COLLECTION = "modelos_moto"


class ModeloMoto(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str = Field(max_length=60)
    costo_auteco: Money  # costo del modelo (para el lote/inventario Auteco)
    precio_venta_con_iva: Money
    cuota_inicial: Money
    cuota_semanal: Money
    plazo_semanas: int = Field(gt=0)
    matricula: Money
    participacion_mix: Money  # fracción 0..1 (participación en la colocación)
    orden: int
    activo: bool = True
    es_sistema: bool = False

    class Settings:
        name = MODELOS_MOTO_COLLECTION
        # Único por nombre (como Rubro por grupo+nombre). En Mongo real lanza
        # DuplicateKeyError; mongomock no lo exige → se prueba con @requires_real_mongo.
        indexes = [
            IndexModel([("nombre", 1)], name="nombre_unico", unique=True),
            IndexModel([("orden", 1)], name="por_orden"),
        ]
