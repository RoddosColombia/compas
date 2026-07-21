# RESPUESTA KIMI — sprint2-cargas · PR1-I

**Veredicto:** NO-GO condicionado — **8.8 / 10** (umbral 9.0). Fecha: 2026-07-20.

Reconocido: §1.12 fiel al contrato (scope único, TTL E-6, replay con status original probado, 422 payload distinto, 409 en curso, key fallida no se quema), F-04 con ULID propio, valor string anti-number, F-22 (.xlsm/10MB/413), mapeo de errores exacto, y **proceso correcto (gate antes del merge)**.

## Hallazgos
- **M-1** — Creación manual SIN rubro explícito queda sin evento permanente (la IdempotencyKey expira a 24h → forensemente invisible). El POST manual es la única vía de dinero sin archivo de banco. **Corrección exigida: CR al catálogo (patrón E-9) añadiendo `transaccion.creada`** y emitirla en TODA creación manual (+ test).
- **M-2** — F-22 incompleto: falta tope de filas (~20.000) y ratio de descompresión (Spec §1.6). Fix: contar filas en el loop → fallida si excede (+ test 20.001).
- **B-1** — Carrera del índice idempotente cae en 500; capturar `DuplicateKeyError` del insert → 409.
- **B-2** — Falta test de Consulta 403 en `/cargas`.

## Decisiones declaradas
D1 → exige la CR (M-1). D2 (idempotencia solo en POST manual) correcta. D3 (key fallida no se quema) correcta. D4 (happy path vía servicio) suficiente. RBAC 403 para Consulta correcto (M13.1).

**Camino:** M-1 + M-2 + B-1 + B-2 → diff → verificación. Estimación ≥ 9.4 → GO.
