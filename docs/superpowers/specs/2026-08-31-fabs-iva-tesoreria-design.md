# FABS · Provisión de IVA como tesorería (inc6 · #1) — diseño

**Fecha:** 2026-08-31
**Autor:** Andrés (CEO) + Claude
**Estado:** aprobado para plan (GO CEO 2026-08-31)
**Rama:** `feat/fabs-iva-tesoreria` (desde `main` a0979ff)
**Contexto:** primera de las 3 piezas de la "evolución" (inc6) de FABS. Las otras dos (escenarios conversacionales, reporte a inversionistas) se diseñan por separado después. Teams: descartado (el comité está en Telegram).

---

## 1. Objetivo

Hacer **accionable** el fondo de provisión de IVA como una función de **tesorería**: que FABS te diga cuánto apartar y si vas cubierto, que el disponible en vivo muestre esa plata como **apartada** (no gastable), y que FABS **avise solo** cuando se acerca la fecha DIAN o el disponible no cubre la reserva. Alineado al norte (IVA mínimo, fecha exacta de pago).

## 2. Norte y alcance

**Qué SÍ (esta pieza):**
- **Advisory de FABS** (conversacional): una tool nueva que expone el estado del fondo (objetivo de reserva, próximo pago + fecha DIAN, cobertura vs disponible).
- **La cerca**: el disponible en vivo muestra **bruto** y **neto de IVA** (bruto − objetivo de reserva), transparente.
- **Proactivo**: un 4º job del vigilante que avisa (borrador→publicar) cerca de la fecha DIAN o si el disponible no cubre la reserva.

**Qué NO (fuera de alcance / fast-follows):**
- Trackear la reserva REAL como plata apartada de verdad (sub-cuenta / captura manual). El objetivo es **computado del plan** (decisión CEO 2026-08-31).
- Que la reserva mueva la **caja proyectada** (el fondo sigue informativo; el egreso real del IVA ya está en `meses[].iva` en la fecha DIAN).
- Cambios al motor, a la liquidación de IVA, o a las tools existentes (solo se consumen).
- Pulido visual de la barra (Cowork).

## 3. Decisiones del CEO (2026-08-31)

1. **inc6 = 3 subsistemas** (provisión IVA tesorería + escenarios conversacionales + reporte inversionistas); se diseñan **uno a la vez**. Teams fuera.
2. Provisión de IVA: **ambas** (advisory de FABS + la cerca en el disponible) **y proactivo** (4º job del vigilante).
3. **Objetivo de reserva = computado del plan** (`FondoMes.saldo` del mes actual), sin captura manual.

## 4. Datos base (lo que ya existe, se reusa)

- **Fondo de provisión** — `iva.liquidacion.plan_fondo_provision(...) -> list[FondoMes]`, `FondoMes{mes_idx, reserva, pago, saldo}` (Decimal). `saldo` = acumulado del fondo al cierre del mes. La proyección ya lo expone como serie informativa (`proyeccion.service` → `fondo_provision`).
- **Liquidación de IVA** — `iva.liquidacion.proximo_pago(anio, idx, periodicidad, calendario) -> {fecha, dias} | None`; la tool `iva.iva_cuatrimestre()` (FABS) ya da el **monto neto a pagar + fecha DIAN**.
- **Disponible en vivo** — `cierre.service.conciliacion(mes)["consolidado_reportado"]` (banco + Wava), lo mismo que alimenta la barra de saldo (PR #113).
- **Umbrales/periodicidad** — `PERIODICIDAD_IVA` y `CALENDARIO_DIAN` en `Configuracion` (ya versionados).

**Definición clave — objetivo de reserva a hoy:** el `saldo` del `FondoMes` cuyo `mes_idx` corresponde al mes actual (lo que, según el plan, ya deberías tener apartado para el próximo pago). Cifra de COMPAS, no del CEO.

## 5. Componentes

### 5.1 Advisory de FABS — tool `iva_tesoreria`

Sigue el patrón de las tools existentes: **calc puro** (`cfo/calc/iva_tesoreria.py`, S1: no importa motor/domain — recibe números, arma `ResultadoCFO`) + **wrapper** en `cfo/agente/tools.py` (lee los servicios y pasa los números al calc) + registro en el prompt.

El wrapper reúne: el `FondoMes` del mes actual (de `proyeccion.service` / `plan_fondo_provision`), el próximo pago (monto de `iva.iva_cuatrimestre` + `proximo_pago`), y el disponible (`conciliacion.consolidado_reportado`). El calc arma los `ResultadoCFO` (conceptos namespaced `ivates_*`, unidad COP salvo la nota temporal):

| Concepto | valor | evidencia |
|---|---|---|
| `ivates_reserva_objetivo` | `FondoMes.saldo` (mes actual) | ref `objetivo:acumulado` |
| `ivates_reserva_mes` | `FondoMes.reserva` (mes actual) | ref `aporte:mes` |
| `ivates_proximo_pago` | monto neto del próximo período | `fecha_corte=fecha DIAN`, ref `dias:{n}` → `formatear` lo renderiza "$X (vence el YYYY-MM-DD, en N días)" (reusa la rama existente de `iva_cuatrimestre`) |
| `ivates_disponible_neto` | `consolidado_reportado − reserva_objetivo` | ref `neto:iva` |
| `ivates_faltante` | `max(0, reserva_objetivo − consolidado_reportado)` | ref `cobertura` (0 ⇒ cubierto) |

Abstención honesta (regla 7): sin fondo/sin config de proyección, o sin mes en ejecución / bancos sin reportar → los conceptos afectados salen `disponible=False` (no se inventan). El modelo cita por token; anti-alucinación idéntica al resto.

### 5.2 La cerca — disponible neto de IVA

Un endpoint de lectura que devuelve el disponible **descompuesto** (transparente, no descuento silencioso):

`GET /api/v1/caja/disponible` (o extender la respuesta que ya consume la barra) → `DisponibleTesoreria`:
```python
class DisponibleTesoreria(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    bruto: str            # consolidado_reportado (money str)
    reserva_iva: str      # objetivo de reserva a hoy (money str)
    neto: str             # bruto − reserva_iva (money str, puede ser negativo)
    fecha_corte: str | None
    sin_dato: list[str]   # bancos sin reportar (frescura); no vacío ⇒ bruto parcial
```
RBAC: la misma capacidad con que hoy se lee el saldo (reusar, sin permiso nuevo). Money como string (regla 1). Si no hay fondo/config, `reserva_iva="0"` y `neto==bruto` (la cerca no aplica hasta configurar).

**Frontend:** la barra de saldo muestra los **dos números** — el bruto y, debajo/al lado, "de eso, $X está apartado para el IVA → disponible real $Y". Funcional aquí (Tailwind mínimo); **Cowork** pule. NUNCA `Number` sobre montos (regla 1); se pintan tal cual.

### 5.3 Proactivo — 4º job del vigilante

Evaluador `cfo/vigilante/iva_tesoreria.py` (orquestación; lee servicios; S1) + job diario + `generar_y_entregar_iva()` (espeja `alerta.py`). Dispara cuando:
- **cerca de la fecha DIAN:** `proximo_pago.dias <= ALERTA_IVA_DIAS` (config nueva, default 30), **o**
- **descubierto:** `consolidado_reportado < reserva_objetivo` (el disponible no cubre lo que deberías tener apartado; frescura: se abstiene si `sin_dato`≠[]).

Texto **determinista** (como la alerta de caja): plantilla + cifras por token + verificador. Ejemplos:
- Cerca DIAN: `📅 El IVA del período vence pronto: [[ivates_proximo_pago]]. Objetivo de reserva a hoy: [[ivates_reserva_objetivo]].`
- Descubierto: `🔴 Tu disponible no cubre la reserva de IVA: te faltan [[ivates_faltante]] para el objetivo [[ivates_reserva_objetivo]].`

Flujo `borrador→"publicar iva"` (3er/4º comando del mapa `_COMANDOS_PUBLICAR`). Reusa `AvisoVigilante(tipo='iva_tesoreria', periodo=<YYYY-MM>)` — CERO cambios de modelo; ≤1 borrador pendiente (supersede diario, como la alerta). Config propia: `ALERTA_IVA_ACTIVA` (default OFF, como la alerta de caja) + `ALERTA_IVA_DIAS` (default 30), versionadas en `Configuracion`. **2 eventos nuevos** (`vigilante.iva.generado/publicado`, catálogo 72→74).

## 6. Garantía anti-alucinación

- Advisory: cifras de COMPAS citadas por token; `verificar` antes de sustituir; el modelo nunca escribe el número.
- Proactivo: texto determinista (plantilla + token + verificador), como la alerta de caja; publicar reenvía el texto ya verificado, no recomputa.
- La cerca: el endpoint devuelve strings ya formateados; el front no re-procesa montos.

## 7. Reglas innegociables

- **Dinero = Decimal** backend, string en la API; formateo es-CO; sin float; el front nunca hace `Number` (regla 1).
- **TZ** `now_bogota()`/`today_bogota()`; `dias` a la fecha DIAN vía `proximo_pago`.
- **Pydantic strict** en `DisponibleTesoreria` y los schemas nuevos.
- **`motor.py` 0 diffs** (solo se LEE el fondo/liquidación; el fondo sigue informativo).
- **S1**: calc puro en `cfo/calc`; evaluador/orquestación en `cfo/vigilante`; `cfo/calc` no importa motor/domain.
- **Scheduler solo en el worker** (regla 6); job idempotente; no-op si `CFO_ENABLED` off o `ALERTA_IVA_ACTIVA` off.
- **Catálogo cerrado**: +2 (regla 11).
- **RBAC por dependencia**; sin permiso nuevo (reusar `cfo:consultar` para el advisory; la capacidad del saldo para el disponible).

## 8. Casos borde

- **Sin fondo / sin config de proyección** (`ProyeccionError`): el advisory y el proactivo se abstienen; la cerca devuelve `reserva_iva="0"` (neto==bruto).
- **Sin mes en ejecución / bancos sin reportar**: la cobertura y el disponible neto se abstienen (frescura); el próximo pago/objetivo (que no dependen del disponible) pueden seguir.
- **Sin fecha DIAN en el calendario** (`proximo_pago`→None): se omite la línea de vencimiento (no se inventa; R5).
- **`neto` negativo** (disponible < reserva): se muestra tal cual (con "-$X"); es justo la señal de tesorería.
- **Alerta IVA apagada** (`ALERTA_IVA_ACTIVA` ausente/False): el job es no-op.
- **Reintento de "publicar iva"**: dedup por update_id (ya vigente).

## 9. Testing

- **Calc `iva_tesoreria`:** arma los 5 conceptos con las cifras dadas; abstención cuando falta un insumo; `neto`/`faltante` correctos (incl. negativo/cubierto).
- **Tool + wrapper:** lee fondo+liquidación+disponible (fakes), pasa al calc; el modelo cita por token; sin cifra cruda.
- **Endpoint `/caja/disponible`:** bruto/reserva/neto correctos; `reserva_iva=0` sin fondo; RBAC + frescura (`sin_dato`).
- **Evaluador + job:** dispara por DIAN-cercano y por descubierto; se abstiene sin config / sin dato bancario; no-op con flag/alerta off; supersede diario.
- **Publicar `iva`:** difunde el borrador tipo `iva_tesoreria`, marca publicado, audita `vigilante.iva.publicado`; no toca los otros tipos; match exacto; dedup.
- **Auditoría:** `generado`/`publicado` en `audit_log`; catálogo 74.
- **Frontend:** la barra muestra bruto + neto-de-IVA; no hace `Number` sobre montos; `npm run build` verde.
- **Guardas:** `motor.py` 0 diffs; S1; sin float de dinero.

## 10. Fuera de alcance / fast-follows

- Trackear la reserva real como plata apartada (sub-cuenta declarada por el CEO).
- Que la reserva mueva la caja proyectada.
- Pulido visual de la barra (Cowork).
- Las otras 2 piezas de inc6 (escenarios conversacionales, reporte a inversionistas) — specs aparte.
- Go-live: el mismo worker `compas-jobs` corre el 4º job; encender `ALERTA_IVA_ACTIVA` (default OFF).
