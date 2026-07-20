# RESPUESTA KIMI — sprint1-parsers · PLAN-I

## Veredicto: **GO — 9.2/10** (umbral ≥ 9.0), con 1 precisión obligatoria (M-1)
Plan scope-exacto (coincide con PLAN_TRABAJO Sprint 1; difiere BBVA/Global66/clasificación/
mini-migración a Sprint 2 sin sobre-alcance) y caza las 3 trampas del port desde SISMO-V2 antes de
codificar: (a) `id_banco` inexistente → precondición + CR, no adivinanza; (b) float/US-format al leer
.xlsx → Decimal + locale es-CO; (c) `continue` silencioso → todo-o-nada con `fallida` + `motivo_fallo`.
Orden de PRs por dependencia correcto. **Construir apenas cierre el Gate G1.**

## M-1 (obligatoria) — contenido mínimo de la CR de la Decisión A2
Una clave determinista ingenua (`hash(fecha+descripcion+valor)`) colapsaría dos movimientos legítimos
idénticos el mismo día → el dedup borraría dinero real (falso positivo, el peor fallo). La CR de A2
DEBE exigir: (1) clave con **posición en el extracto** (`banco, sha256(archivo_hash||nro_fila)`),
nunca solo contenido; o (2) usar **saldo corrido** como rompe-empates; y (3) **análisis de colisión
sobre los fixtures reales congelados** como evidencia. Si el layout revela ID nativo (A1), se archiva.
→ **APLICADA** en `PLAN.md` (Decisión A, nota de la CR de A2).

## Bajas — APLICADAS
- `Decimal(repr(celda))` para numéricas (no `str()`); normalización es-CO para texto. → aplicada en Decisión B.
- Placeholder de dedup parcial (`test_real_mongo_marker`) se implementa en PR-1 (esquema+dedup). → ya en PR-1.
- Confirmar que el layout congelado (fixture real anonimizado) es el PRIMER entregable commitado antes
  del parser (F-51). → ya en PR-2 (orden explícito).

## Camino
Incorporar M-1 a la futura CR de A2 → arrancar PR-1 (esquema+dedup) tras GO del Gate G1 → gates Kimi por PR.
