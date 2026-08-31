"""FABS · vigilante — arma el texto DETERMINISTA de la alerta de caja. Sin LLM: cada
cifra es un [[token]] respaldado por un ResultadoCFO de COMPAS. Pasa por el verificador
(defensa en profundidad; pasa trivial porque no hay cifras crudas) y luego se
sustituyen los tokens. Mismo contrato anti-alucinación que el resto de FABS."""

from app.cfo.agente.conceptos import sustituir_tokens
from app.cfo.agente.verificador import verificar
from app.cfo.vigilante.disparadores import ResultadoAlerta


class AlertaTextoError(RuntimeError):
    """El verificador rechazó el texto de la alerta (no debería ocurrir: es
    determinista y sin cifras crudas). Fail-loud para no difundir algo sin verificar."""


_ENCABEZADO = "🚨 Alerta de caja — FABS"

# Ninguna plantilla contiene un dígito crudo (chocaría con el verificador).
_LINEAS: dict[tuple[str, str], str] = {
    ("proyectado", "ambar"): (
        "⚠️ La caja proyectada entra en zona de atención: el piso baja a "
        "[[alerta_piso]], por debajo del umbral de atención [[alerta_umbral_atencion]]."
    ),
    ("proyectado", "rojo"): (
        "🔴 La caja proyectada cae bajo el mínimo: el piso [[alerta_piso]] cruza el "
        "crítico [[alerta_umbral_critico]]."
    ),
    ("real", "ambar"): (
        "⚠️ El disponible real de hoy [[alerta_disponible_hoy]] está en zona de "
        "atención, bajo el umbral [[alerta_umbral_atencion]]."
    ),
    ("real", "rojo"): (
        "🔴 El disponible real de hoy [[alerta_disponible_hoy]] está bajo el mínimo "
        "[[alerta_umbral_critico]]."
    ),
}


def construir_texto(res: ResultadoAlerta) -> tuple[str, str]:
    cuerpo = "\n".join(_LINEAS[(d.tipo, d.severidad)] for d in res.disparos)
    crudo = f"{_ENCABEZADO}\n\n{cuerpo}"
    ver = verificar(crudo, res.resultados)
    if not ver.ok:
        raise AlertaTextoError(
            f"alerta rechazada por el verificador: cifras={ver.cifras_sin_evidencia} "
            f"tokens_invalidos={ver.tokens_invalidos}"
        )
    return crudo, sustituir_tokens(crudo, res.resultados)
