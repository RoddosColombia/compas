# FABS · Reporte a inversionistas (inc6 · #3) — diseño

**Fecha:** 2026-09-08
**Autor:** Andrés (CEO) + Claude
**Estado:** aprobado para plan (GO CEO 2026-09-08)
**Rama:** `feat/fabs-reporte-inversionistas` (desde `main` f94ebc5)
**Contexto:** 3ª y última pieza de la "evolución" (inc6) de FABS. inc6 #1 (IVA tesorería) MERGEADO `c0f9bfe`; #2 (escenarios conversacionales) pendiente. Teams descartado.

---

## 1. Objetivo

FABS genera **a demanda** un **documento formal (.docx) para inversionistas** — narrativa + cifras de COMPAS + una gráfica del rumbo de caja — que el CEO **revisa y envía por fuera**. La historia a inversionistas es la **trayectoria a la sostenibilidad**: dónde está la caja y su rumbo hacia el umbral de mayo-2027, con un recap del período.

## 2. Norte y alcance

**Qué SÍ:**
- Endpoint a demanda que arma un **.docx** con 5 secciones (recap + prospectivo), cifras deterministas en tablas, narrativa de FABS, y una **gráfica embebida** del rumbo de caja (matplotlib).
- El CEO lo descarga, lo revisa (es editable) y lo envía por fuera (email/lo que use). Sin difusión automática (los inversionistas no están en el comité de Telegram).

**Qué NO (fuera de alcance / fast-follows):**
- Envío automático a inversionistas / lista de destinatarios (el CEO envía por fuera).
- Job proactivo / trimestral automático (se eligió "a demanda").
- PDF (se eligió .docx editable).
- Pulido visual fino del documento y de la gráfica (Cowork).
- Cambios al motor, a las tools, o a la liquidación (solo se consumen).

## 3. Decisiones del CEO (2026-09-08)

1. **Formato:** `.docx` (Word, editable — el CEO ajusta antes de enviar).
2. **Contenido:** ambos (recap + prospectivo), **énfasis prospectivo** (rumbo al umbral).
3. **Gráfica:** embebida en v1 (matplotlib — dep nueva).
4. **Cadencia/disparo:** a demanda (el CEO lo pide), no job.

## 4. Arquitectura y flujo

```
[el CEO pide el reporte]  → POST /api/v1/cfo/reporte-inversionistas  (RBAC export:reportes; guard 404 si CFO_ENABLED off)
        │
        ▼
cfo/reporte/datos.reunir_datos()  (orquestación; lee servicios vigentes — figuras deterministas por sección)
   ├─ caja/runway/rumbo (proyeccion) · mix/colocación (modelos_moto) · gasto (composicion + real_vs_presupuesto) · deuda/IVA
   └─ narrativa: consultar() con prompt de reporte (cita cada cifra por token; verificado; el modelo NO escribe números)
        │
        ▼
cfo/reporte/grafica.render_rumbo(serie)  (matplotlib Agg, lazy import) → PNG bytes
        │
        ▼
cfo/reporte/documento.armar_docx(datos, narrativa, png)  (python-docx) → .docx bytes
        │
        ▼
Response(.docx, media_type=…wordprocessingml.document, Content-Disposition attachment; filename reporte-inversionistas-YYYY-MM.docx)
```

Todas las cifras las computa COMPAS (servicios vigentes) — las tablas y la narrativa leen la **misma proyección vigente**, así son consistentes. El CEO revisa el borrador (humano en el loop) antes de enviar.

## 5. Componentes

### 5.1 Endpoint + descarga

`POST /api/v1/cfo/reporte-inversionistas` en `backend/app/cfo/reporte/router.py` (o extendiendo `cfo/router.py`):
- RBAC `require_permission("export:reportes")` (financiero/directivo/admin — ya existe, **sin permiso nuevo**). Guard 404 si `not cfo_enabled()`.
- Body opcional `{periodo?: "YYYY-MM"}` — default: el estado vigente (recap = último mes cerrado; proyección = desde hoy).
- Devuelve el `.docx` como descarga: `Response(content=<bytes>, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="reporte-inversionistas-{periodo}.docx"'})`. **Primer endpoint de descarga de archivo del backend** — patrón nuevo, aislado.

### 5.2 Datos por sección (`cfo/reporte/datos.py`, orquestación)

`async def reunir_datos(periodo: str | None) -> DatosReporte` — lee los servicios vigentes y arma las cifras (Decimal→`money_str`) de las 5 secciones. Reusa lo que ya existe (mismos servicios que las tools de FABS):
1. **Resumen ejecutivo** — caja disponible hoy + piso proyectado + si/ cuándo cruza el umbral (mayo-2027) + runway.
2. **Caja y rumbo al umbral** — serie de caja proyectada (para la gráfica) + `caja_minima`/`caja_atencion` + mes de quiebre. *(prospectivo)*
3. **Ventas / colocación** — mix de modelos + tendencia de ingreso + motos para evitar el umbral (`escenario.motos_para_evitar_umbral`).
4. **Gasto y eficiencia** — composición del gasto (grupos) + real vs presupuesto del último cerrado. *(recap)*
5. **Deuda / obligaciones** — próximos vencimientos + IVA (`iva`/`iva_tesoreria`).
Abstención honesta (regla 7): sin config de proyección / sin datos, la sección afectada dice "sin datos", no inventa.

`DatosReporte` es un modelo Pydantic strict (todas las cifras como `str` es-CO / `money_str`).

### 5.3 Narrativa (FABS)

El resumen ejecutivo y un comentario corto por sección los **narra FABS** vía `consultar()` con un prompt de reporte a inversionistas (factual, conservador, sin promesas; cita cada cifra por token). Contrato anti-alucinación idéntico: `verificar` antes de sustituir; el modelo nunca escribe un número; solo texto ya verificado entra al documento. Como `consultar` y las tablas leen la misma proyección vigente, las cifras coinciden. **El CEO revisa antes de enviar** (humano en el loop cubre el tono/las afirmaciones de la prosa).

### 5.4 Gráfica del rumbo (`cfo/reporte/grafica.py`)

`def render_rumbo(meses: list[dict], caja_minima: str, caja_atencion: str | None) -> bytes` — renderiza la curva de caja proyectada + la línea del umbral (y la banda de atención si está) como **PNG**. Usa matplotlib con **backend `Agg`** (no-interactivo, server-side): `import matplotlib; matplotlib.use("Agg")` **antes** de `pyplot`, e **import perezoso dentro de la función** (matplotlib es pesada — no cargarla al arrancar el web; solo cuando se pide un reporte). Colores es-CO neutrales; sin dependencia del frontend. Money para las etiquetas del eje se formatea con las mismas reglas (no float sobre valores; el eje usa los Decimal ya calculados).

### 5.5 Documento (`cfo/reporte/documento.py`)

`def armar_docx(datos: DatosReporte, narrativa: dict, png_rumbo: bytes) -> bytes` — arma el `.docx` con **python-docx**: portada/título (RODDOS · Reporte a inversionistas · <periodo>), las 5 secciones (encabezado + narrativa + tabla de cifras), y la gráfica embebida (`add_picture` desde el PNG en un `BytesIO`). Devuelve los bytes del documento (`doc.save(BytesIO)`). Función pura (datos+png in, bytes out — sin I/O de servicios ni dominio).

### 5.6 Dependencias nuevas (runtime)

- `python-docx` (import `docx`) — ensamblado del .docx.
- `matplotlib` — gráfica server-side (backend Agg, import perezoso).
Ambas a `backend/requirements.txt`. **Costo de deploy anotado:** matplotlib es pesada (~más MB en el backend); mitigado por el import perezoso (no afecta el arranque/cold-start del web; solo carga en la 1ª generación de reporte). Documentar en el runbook.

## 6. Garantía anti-alucinación

- **Cifras deterministas:** todas salen de servicios de COMPAS (`money_str`), en tablas — el LLM no computa ni escribe números.
- **Narrativa:** vía `consultar` (verifica el crudo antes de sustituir; cita por token). Tablas y narrativa leen la misma proyección vigente → consistentes.
- **Documento externo:** el CEO **revisa antes de enviar** (humano en el loop) — cubre el tono y las afirmaciones de la prosa, además del contrato anti-alucinación.
- La gráfica se dibuja de la serie proyectada de COMPAS (no del LLM).

## 7. Reglas innegociables

- **Dinero = Decimal** backend, string en la API/tablas; formateo es-CO; sin float (tampoco en las etiquetas del eje de la gráfica) (regla 1).
- **TZ** `now_bogota()`/`today_bogota()`; `periodo` `YYYY-MM`.
- **Pydantic strict** en `DatosReporte` y el body del endpoint.
- **`motor.py` 0 diffs** (solo se LEE la proyección).
- **S1**: `cfo/reporte/grafica.py` y `documento.py` son transformaciones puras (no importan motor/domain); `datos.py` es orquestación (lee servicios). `cfo/calc` intacto; `test_s1_aislamiento` verde.
- **RBAC por dependencia** `export:reportes` (sin permiso nuevo). Guard 404 con flag off.
- **Sin secretos**; el .docx no incluye datos sensibles más allá de las finanzas de RODDOS (es su propio reporte).

## 8. Casos borde

- **Sin config de proyección / sin datos:** las secciones afectadas dicen "sin datos"; el reporte se genera igual (no revienta); la gráfica se omite o muestra solo lo real si no hay proyección.
- **`consultar` se abstiene:** la narrativa cae a un texto mínimo factual (o se omite el comentario), las tablas siguen; el documento se genera.
- **matplotlib no disponible / falla el render:** el reporte se genera **sin** la gráfica (fail-soft: una sección de gráfica ausente no tumba el documento) + log.
- **periodo inválido:** 422 (validación del body).
- **Documento vacío de cifras** (todo abstenido): se genera con los "sin datos" honestos (no se inventa).

## 9. Testing

- **`datos.reunir_datos`:** arma las 5 secciones con cifras de servicios fakeados; abstención por sección sin config; money como string.
- **`grafica.render_rumbo`:** devuelve bytes PNG no vacíos (magic `\x89PNG`) de una serie dada; backend Agg (no requiere display); sin float sobre montos.
- **`documento.armar_docx`:** produce un `.docx` válido — round-trip con python-docx (`Document(BytesIO(bytes))`) abre, tiene los 5 encabezados de sección + al menos una imagen embebida; función pura.
- **Endpoint:** RBAC (401 sin token / 403 sin `export:reportes`), 404 con flag off, 200 devuelve `media_type` de docx + `Content-Disposition: attachment`; el `consultar` se fakea (no LLM real en test).
- **Anti-alucinación:** la narrativa pasa por `verificar` (test que un `%`/cifra cruda del modelo sigue bloqueado); las tablas usan `money_str`.
- **Guardas:** `motor.py` 0 diffs; S1 verde; sin float de dinero; `python-docx`/`matplotlib` en requirements.

## 10. Fuera de alcance / fast-follows

- Envío automático / lista de inversionistas.
- Trimestral automático (5º job).
- PDF además del docx.
- Pulido visual del documento y la gráfica (Cowork).
- La pieza inc6 #2 (escenarios conversacionales) — spec aparte.
- Go-live: `CFO_ENABLED` ya ON; el endpoint queda disponible al mergear para quien tenga `export:reportes`. Anotar en el runbook la dep matplotlib (tamaño del backend).
