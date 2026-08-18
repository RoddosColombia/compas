# EVIDENCIA — FABS inc3 Pieza A (verificación por concepto) · CÓDIGO

- **Rama:** `feat/fabs-inc3a-concepto` · **Rango:** `61ded9c..6de54ef` · **Fecha:** 2026-08-17
- **Diff completo del backend:** `inc3a-backend.diff` (esta carpeta, 1027 líneas). Reproducible: `git diff 61ded9c..6de54ef -- backend/`

## 1. Inventario (`git diff --stat`)

```
 backend/app/cfo/agente/conceptos.py          |  65 ++   (NUEVO: RE_TOKEN compartido, formatear server-bound, sustituir_tokens)
 backend/app/cfo/agente/prompt.py             |  59 ++   (cita con [[token]] exacto, nunca escribe números)
 backend/app/cfo/agente/servicio.py           |  17 ++   (sustituye tras verificar; correctivo con tokens)
 backend/app/cfo/agente/tools.py              |  10 ++   (resultado_a_dict sin valor/detalle)
 backend/app/cfo/agente/verificador.py        | 131 ++   (nuevo contrato: cifras crudas prohibidas + tokens; RE_TOKEN importado)
 + 5 archivos de test (conceptos/prompt/servicio/tools/verificador)
 10 files changed, 508 insertions(+), 264 deletions(-)
```
Diff completo vs `61ded9c`: **solo `app/cfo/agente/*` + sus tests** (nada más del backend).

## 2. Motor intocable / flag-off (verificado)

```
$ git diff 61ded9c..6de54ef -- backend/app/proyeccion/motor.py
(vacío — CERO diffs)

$ python -m ruff check app/cfo/
All checks passed!
```
- El único cambio de comportamiento (el modelo no ve `valor`) vive tras el flag `CFO_ENABLED` (apagado ⇒ COMPAS byte-idéntico). `resultado_a_dict` tiene un solo consumidor (`loop.py`) dentro del camino con flag. `app/cfo/calc/*` sin cambios. S1 sigue verde (conceptos.py importa solo `evidencia`+`core.time`).

## 3. Tests (verde)

- **Suite backend completa:** `1044 passed / 95 skipped (requires_real_mongo) / 0 failed`, flag apagado.
- Núcleo verificador+conceptos+servicio: `34 passed`; `tests/cfo/`: `82 passed`.
- Casos clave: el **vinculante** (`test_el_caso_vinculante_caja_con_valor_de_iva_se_rechaza` — el modelo escribe crudo el valor del IVA bajo etiqueta caja → rechazo); token inválido/no-disponible → rechazo; **sustitución** ([[caja_hoy]]→$704.722.003, [[iva]]→"…en 24 días"); **D-3 tope de reintento** (reincidencia → abstención, 1 reintento, jamás loop, ×2 tests); token con espacios `[[ caja_hoy ]]` valida+sustituye; `resultado_a_dict` sin `valor`. Todo con `ClienteFake` (sin API key).

## 4. Trazabilidad (gate + SDD)

- **Gate de DISEÑO Kimi: 9.3 GO** (D-1 interpretación server-bound + D-3 tope de reintento aplicados al spec).
- Construido por **SDD**: 6 tareas, subagente fresco + review de dos etapas por tarea. Fix rounds cerrados: T1 (test del fallback today_bogota), T3 (re-cubrir catch de bare-digit + docstring de huecos residuales).
- **Review final whole-branch (opus): "Ready to merge — Yes", 0 Critical/0 Important.** Fix wave recomendado aplicado (RE_TOKEN compartido + tolerante a espacios → drift imposible entre validar/sustituir); re-review scoped "all addressed".
- Rulings del controlador (SDD): Ruling-1 (tests de `valor` reemplazados, obsoletos por diseño), Ruling-2 (test_verificador reescrito al nuevo contrato, preservando "fabricación se atrapa").

## 5. Huecos residuales declarados (radar del piloto, aceptados — no se cierran aquí)

- Aritmética en prosa ("el doble de antes"), enteros pelados <5 díg sin separador, números en palabras ("mil millones") — no los detecta ningún regex; mitigación = prompt regla #1 + abstención. `[[caja hoy]]` con espacio DENTRO del identificador (2 palabras) no matchea (conceptos son snake_case).
- Nota pre-existente de `iva.py` (no de esta pieza): sep 1-10, el período vigente voltea a sep-dic mientras el may-ago vence en ≤9 días → el "vence en N días" no aplica a ese deadline. Radar del piloto.
