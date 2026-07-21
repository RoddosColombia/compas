# RESPUESTA KIMI — sprint3-ciclo · PR1-I

**Veredicto:** NO-GO condicionado — **8.8 / 10** (umbral 9.0). Fecha: 2026-07-21.

Reconocido: compensación O1 exacta (test 0-residuo), unicidad→409, RBAC §2.4 con tests bilaterales, montos string, manual rechazado, proceso maduro (CI replica set + pip-audit con CVEs reales).

## M-1 (Media, semántica) — `saldo_inicial_caja` debe DERIVARSE, no ser input libre
US-01 ("arrastra saldo de caja del cierre") + Spec §1.3/F-14 ("al cerrar el mes anterior se fija = saldo bancario consolidado reportado; editable solo Admin+step-up"). Hoy el endpoint lo pide siempre → digitación errada = caja desviada TODO el mes con apariencia válida (falla silenciosa).
**Corrección:** con predecesor → derivar del consolidado bancario anterior; input obligatorio SOLO para el primer mes de la historia; override manual = `ciclo:config`+step-up (futuro). **Test: abrir N+1 → saldo == cierre de N.**

## Bajas
- **B-1:** smoke de imports con SOLO requirements.txt en CI (atrapa el drift runtime/dev del incidente python-multipart).
- **B-2:** falta test del rechazo de `manual` en saldos (código sí, test no).
- **B-3:** GET /meses sin paginación — aceptable para el selector; nota futura.

## Decisiones declaradas — todas aceptadas
Sin Idempotency-Key ✓ · sin transacción ✓ (razón estructural: mes y audit viven en conexiones/roles distintos — una transacción Mongo no puede abarcarlas; la compensación es la herramienta correcta) · apertura sin sugerido ✓ (motor llega en Sprint 3 antes de la demo) · saldos_banco opcional ✓.

**Camino:** M-1 + B-1 + B-2 → diff → verificación. Estimación ≥ 9.4 → GO.
