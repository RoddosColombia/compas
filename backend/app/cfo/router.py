# backend/app/cfo/router.py
"""FABS · POST /api/v1/cfo (chat embebido) + GET /api/v1/cfo/historial. Doble
barrera: (1) solo se monta en main si CFO_ENABLED (app/main.py::create_app); (2)
guard 404 defensivo en cada handler si se alcanza con el flag apagado (p. ej. si
alguien apaga la env var en caliente sin reiniciar el proceso — cfo_enabled() lee
el entorno en cada llamada, sin cache).

POST es conversacional sobre el HILO COMPARTIDO con Telegram (mismo user_id): lee
el historial crudo (`hilos.historial_para_loop`, ventana `config.cfo_hilo_ventana`),
se lo pasa a `servicio.consultar` y persiste el turno web (`hilos.registrar_turno_web`)
para que el próximo turno — de cualquier canal — lo re-alimente. GET /historial sirve
el scrollback ya sustituido (`hilos.historial_para_display`), nunca el crudo con
tokens.

RBAC: require_permission('cfo:consultar') (Regla 9: nunca require_role en negocio)
en ambos endpoints. Money/cifras viajan como string dentro de RespuestaCFO (regla 1);
el body de la consulta es texto libre, no dinero."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.auth.deps import require_permission
from app.auth.models import User
from app.cfo import config
from app.cfo.agente import servicio
from app.cfo.agente.modelos import RespuestaCFO
from app.cfo.config import cfo_enabled
from app.cfo.telegram import hilos, repositorio

router = APIRouter(prefix="/api/v1/cfo", tags=["cfo"])


class ConsultaBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    pregunta: str


class TurnoHistorial(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    rol: str
    texto: str
    canal: str
    ts: str | None = None


@router.post("", response_model=RespuestaCFO)
async def consultar(
    body: ConsultaBody,
    user: User = Depends(require_permission("cfo:consultar")),
) -> RespuestaCFO:
    if not cfo_enabled():  # guard defensivo (barrera 2)
        raise HTTPException(404, "No encontrado.")
    uid = str(user.id)
    hilo = await repositorio.obtener_hilo(uid)
    historial = hilos.historial_para_loop(hilo, config.cfo_hilo_ventana())
    resp = await servicio.consultar(body.pregunta, actor_id=uid, historial=historial)
    await hilos.registrar_turno_web(uid, body.pregunta, resp.texto_crudo, resp.texto)
    return resp


@router.get("/historial", response_model=list[TurnoHistorial])
async def historial(
    user: User = Depends(require_permission("cfo:consultar")),
) -> list[dict]:
    if not cfo_enabled():  # guard defensivo (barrera 2)
        raise HTTPException(404, "No encontrado.")
    hilo = await repositorio.obtener_hilo(str(user.id))
    return hilos.historial_para_display(hilo)
