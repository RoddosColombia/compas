# backend/app/cfo/router.py
"""FABS · endpoint POST /api/v1/cfo (incremento 2). Doble barrera: (1) solo se
monta en main si CFO_ENABLED (app/main.py::create_app); (2) guard 404 defensivo en
el propio handler si se alcanza con el flag apagado (p. ej. si alguien apaga la env
var en caliente sin reiniciar el proceso — cfo_enabled() lee el entorno en cada
llamada, sin cache).

RBAC: require_permission('cfo:consultar') (Regla 9: nunca require_role en negocio).
Money/cifras viajan como string dentro de RespuestaCFO (regla 1); el body de la
consulta es texto libre, no dinero."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.auth.deps import require_permission
from app.auth.models import User
from app.cfo.agente import servicio
from app.cfo.agente.modelos import RespuestaCFO
from app.cfo.config import cfo_enabled

router = APIRouter(prefix="/api/v1/cfo", tags=["cfo"])


class ConsultaBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    pregunta: str


@router.post("", response_model=RespuestaCFO)
async def consultar(
    body: ConsultaBody,
    user: User = Depends(require_permission("cfo:consultar")),
) -> RespuestaCFO:
    if not cfo_enabled():  # guard defensivo (barrera 2)
        raise HTTPException(404, "No encontrado.")
    return await servicio.consultar(body.pregunta, actor_id=str(user.id))
