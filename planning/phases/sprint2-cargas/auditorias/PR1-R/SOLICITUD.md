# SOLICITUD DE AUDITORÍA — sprint2-cargas PR1-R: fixes de I-PR1 (8.8 → re-auditoría)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-20
**Ronda previa:** I-PR1 = 8.8 (2 Medias + 2 Bajas). **Fix commit:** `f9985fe` sobre `54f12d6` (rama `feat/cargas-endpoints-manual`, sigue SIN mergear).

## Resolución por hallazgo

| # | Hallazgo | Corrección | Evidencia |
|---|---|---|---|
| **M-1** | Creación manual sin rubro = forensemente invisible | **CR-S2**: evento `transaccion.creada` añadido al catálogo (30→31; regla 11 de CLAUDE.md actualizada; registrada en hoja CRs del tracker). Se emite en **TODA** creación manual, con metadata origen/valor/tipo | `test_toda_creacion_manual_emite_creada` (manual sin rubro → evento con entidad_id y origen 'manual'); catálogo verificado por `test_catalogo_tiene_exactamente_31_eventos` |
| **M-2** | F-22 sin tope de filas ni ratio de descompresión | `MAX_FILAS=20.000` verificado EN el loop de ambos parsers (error explícito antes de gastar CPU) + `_validar_zip` (descomprimido ≤200MB y ratio ≤100) llamado antes de abrir el workbook | `test_tope_20001_filas_real` (archivo REAL de 20.001 filas → rechazo), `test_tope_de_filas` (parametrizado), `test_zip_bomb_rechazada` (bomba sintética 60MB de ceros → rechazo) |
| **B-1** | Carrera del índice idempotente → 500 | `DuplicateKeyError` del insert de la marca → **409** | `test_carrera_idempotency_key_da_409` (simulado con monkeypatch; el índice único `scope_unico` es quien lo dispara en real) |
| **B-2** | Falta test Consulta 403 en /cargas | Añadido (GET y POST) | `test_consulta_403_en_cargas` |

## Nota sobre la CR-S2
Tu M-1 avaló la CR ("tu propia propuesta era la correcta"). Queda registrada en la hoja CRs del tracker con patrón E-9 (se folda al re-baseline v1.1.3 junto con los 2 eventos MFA de E-9). Mientras tanto: `events.py` + regla 11 + tests ya reflejan 31.

## Semántica preservada
El resto del PR (I-PR1 8.8) sin cambios: §1.12, ULID, F-22 extensión/tamaño, RBAC, pantalla de cargas (frontend, commit `a057ba2`, no crítico).

## Evidencia local (EVIDENCIA.md: diff de fixes + salidas)
- pytest: **238 passed / 23 skipped** (6 nuevos vs I-PR1). ruff limpio. Greps protocolo: 0.
- Frontend: vitest 7/7, biome limpio, build OK (sin cambios en esta ronda).
