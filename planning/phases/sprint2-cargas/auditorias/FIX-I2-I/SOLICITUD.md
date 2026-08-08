# SOLICITUD DE AUDITORÍA — FIX-I-2: dedup F-02 con read concern linearizable

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-08-08 · **Área:** cargas bancarias (crítica)
**Rama / PR:** `fix/i2-dedup-linearizable` · commit `ba18d79`
**Antecedente:** FIX-I (PR #57, `ab4fd77`) — "dedup F-02 con read concern majority (elimina flake de CI)". El flake **volvió** (lo vimos en el gate de E1-P6: `backend-real-mongo` falló, pasó al re-run).

## Diagnóstico (systematic-debugging, investigación primero)

**Bug:** `test_carga.py::TestServicioCarga::test_s3_dedup_no_re_sube` (real-mongo) intermitente:
la 2ª carga del mismo archivo a veces **NO lanza** `CargaDuplicadaError` ("DID NOT RAISE") → el
`find_one` de dedup no ve la carga previa `COMPLETADA`.

**Contrato de consistencia (leído en el código):**
- **Escritura** de `estado=COMPLETADA`: dentro de `session.with_transaction` (`service.py`, `_finalizar` → `carga.save(session=session)`) → commit **w:majority**.
- **Lectura** de dedup (antes): `find_one` con `ReadConcern("majority")` en una **operación nueva sin sesión causal**.

**Causa raíz:** `majority` read concern garantiza leer datos *ya confirmados por mayoría*, **NO el
ÚLTIMO** commit. Sin **consistencia causal** (`afterClusterTime`), una operación nueva puede leer un
snapshot de mayoría **anterior** al commit `COMPLETADA` de la carga previa (**read-after-write causal
gap** del replica set) → el dedup se salta de forma intermitente. FIX-I aplicó `local→majority`
(necesario) pero es **solo la mitad del contrato**; por eso el flake reaparece.

**Evidencia:** (1) el commit de FIX-I nombra el gap y su comentario describe el mecanismo; (2) CI mongo
es **RS de 1 nodo** (`3ea59b8`) → el gap es real bajo carga; (3) lectura y escritura previa están en
operaciones/sesiones distintas sin propagación de `clusterTime`.

## Fix (mínimo, en la causa raíz — solo la lectura)

`ReadConcern("majority")` → **`ReadConcern("linearizable")`** en el `find_one` de dedup + `max_time_ms=5000`.
`linearizable` refleja **todos** los writes majority-ack **completados antes de iniciar la lectura**
(lee del primario y confirma liderazgo) → el guard es **determinista** ante dos cargas del mismo
archivo muy seguidas. **Escritura y lógica intactas** (diff: 1 archivo, la línea del read concern + el
`max_time_ms` + comentario).

- **Por qué linearizable y no una sesión causal:** cross-call (la escritura fue en una llamada previa
  con su sesión) no hay token causal que propagar sin plumbing; `linearizable` da la garantía
  "leer el último write confirmado" por definición, en el primario, sin sesión compartida. Coste: un
  round-trip de confirmación de mayoría por dedup (raro) — despreciable; `max_time_ms` lo acota.
- **Requisitos de linearizable cumplidos:** lectura en el **primario** (directConnection), **fuera de
  transacción**, filtro que identifica **un solo documento** (`archivo_hash` + `estado=COMPLETADA`).

## Validación (declaro la limitación con honestidad)

- **No pude reproducir localmente:** Docker Desktop apagado y sin `mongod` local → no hay RS para el
  stress loop. Decisión CEO: fix directo + validar en CI. **Un run verde de CI no prueba al 100% que
  el flake desapareció** (es de timing); la confianza viene de que el fix es la **garantía documentada
  correcta** para read-after-write cross-client, y de que ataca exactamente el mecanismo que FIX-I dejó
  a medias.
- **Regresión mongomock completa:** ver `EVIDENCIA.md`. Los `@requires_real_mongo` (incl. el test del
  flake) se validan en el job `backend-real-mongo` de CI.
- **ruff** limpio. Greps del protocolo (r1/journal-entries/pending) = 0.

## Puntos a auditar con lupa

1. ¿`linearizable` es la garantía correcta y suficiente para este read-after-write cross-client, y
   supera de verdad a `majority` (que era la mitad)? ¿Alguna preferencia por sesión causal en su lugar?
2. Requisitos de linearizable (primario, fuera de transacción, single-doc, `max_time_ms`): ¿todos OK?
3. ¿El fix deja **escritura/lógica intactas** (solo el read concern de la lectura de dedup)?
4. ¿Riesgo de `max_time_ms=5000` (p. ej. abortar el guard si mongo va lento)? ¿valor razonable?

## Cumplimiento

TDD: no hay test RED nuevo determinista posible (flake de timing no reproducible localmente; documentado
como excepción de systematic-debugging). El test de comportamiento existente (`test_s3_dedup_no_re_sube`)
valida en CI real-mongo. Dinero/histórico: sin cambios. Solo lectura de dedup.
