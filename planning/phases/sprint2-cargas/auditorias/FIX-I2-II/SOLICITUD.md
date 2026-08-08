# SOLICITUD DE AUDITORÍA — FIX-I2-II: flake dedup = timestamps de openpyxl (fix del TEST)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-08-08 · **Área:** cargas bancarias (crítica)
**Rama:** `fix/i2-dedup-test-timestamps` · commit `b1dccc2` · **PR nuevo** (PR #74 CERRADO)
**Ronda anterior:** FIX-I2-I **7.5 NO-GO** — causa raíz equivocada (linearizable = placebo). Este paquete corrige el enfoque con tu causa raíz **demostrada**.

## Acepto el NO-GO y reconozco el fallo de método

En FIX-I2-I declaré la Iron Law y luego **fijé una causa raíz sin validarla** (no reproduje) y
además **imposible** bajo mis premisas (RS 1 nodo + w:majority + awaits secuenciales → una lectura
majority posterior debe ver el write). La evidencia estaba a 40 líneas del test que ya tenía abierto.
La lección: **en depuración la causa raíz se demuestra o no se toca.**

## Causa raíz REAL — reproducida por mí (tu hipótesis, validada)

`_procesar_s3` → `_crear_bbva` **regenera el xlsx en cada llamada** (`openpyxl.Workbook()`+`wb.save()`
sin timestamps fijos). openpyxl **embebe `now()`** en `docProps/core.xml` y en las entradas del zip
(precisión de 1 s). El dedup F-02 es **sha256 de los bytes**. Por tanto la "misma" carga solo es
byte-idéntica si las dos escrituras caen en el **mismo segundo**.

**Prueba ejecutada localmente (sin Mongo, sin Docker, mismas filas del test):**

```
regenerado mismo segundo : IDENTICO (22933016d8c0 vs 22933016d8c0) -> dedup dispara -> test PASA
regenerado tras 1.1s     : DIFIERE  (22933016d8c0 vs 253ee98cdf7c) -> dedup NO dispara -> DID NOT RAISE (flake)
MISMO archivo (fix)      : IDENTICO (22933016d8c0)                  -> determinista, siempre dispara
```

Explica el 100% de lo observado: la **intermitencia** (¿cruzaron un segundo?), por qué solo aparece
en **`backend-real-mongo`** (único job donde corre este test y el más lento → la 1ª llamada cruza el
segundo), por qué **FIX-I (majority) no lo arregló** (nunca fue de consistencia), y por qué el CI con
linearizable pasó una vez (azar: mismo segundo). **El dedup F-02 funciona bien: bytes distintos =
archivos distintos.**

## Fix (pequeño, determinista, en el TEST)

`_procesar_s3(..., crear=True)`: la 2ª llamada del test de dedup usa **`crear=False`** → reprocesa el
**MISMO archivo byte a byte** (no lo regenera) → hash idéntico → dedup dispara **siempre**. Preserva la
semántica real de F-02 (mismo archivo subido dos veces). **Diff: solo `tests/test_carga.py`** (1 archivo).

- **`linearizable` REVERTIDO:** era placebo para este flake. `service.py` queda como en main (majority
  de FIX-I, sin tocar). La protección productiva ante doble-clic ya la da la **idempotencia por
  `id_banco`** (probada: carga 4-ago 30 creadas / 11 duplicadas).

## Puntos a auditar

1. ¿El fix es el correcto y suficiente (byte-identidad → determinismo) y preserva la semántica de F-02?
2. ¿`service.py` quedó **exactamente** como main (linearizable revertido, majority intacto)?
3. ¿La prueba de hash es convincente y reproducible?

## Evidencia (ver `EVIDENCIA.md`)

- Prueba de hash (arriba) reproducible en 1 min sin Docker.
- Diff (solo test). Regresión mongomock **910 passed / 0 fallos**. ruff limpio. Greps del protocolo 0.
- El test del flake corre en `backend-real-mongo`; ahora determinista.

## TDD / método

Esta vez: causa raíz **demostrada** (Fase 1 completa con reproducción) antes de tocar. El fix es de
test (no de producción) → no aplica TDD-de-producción; el determinismo se prueba con el experimento de
hash. Sin cambios en dinero/histórico/lógica.
