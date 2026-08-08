# EVIDENCIA — FIX-I2-II (flake dedup = timestamps openpyxl; fix del test)

Rama `fix/i2-dedup-test-timestamps` sobre `main`. commit `b1dccc2`.

## 1. Prueba de la causa raíz (reproducida sin Mongo/Docker, 1 min)

Mismas filas del test (`[("15-03-2026","COMPRA",-50000)]`), replicando `_crear_bbva` + `_hash_archivo`:

```
regenerado mismo segundo : IDENTICO (22933016d8c0 vs 22933016d8c0) -> dedup dispara -> test PASA
regenerado tras 1.1s     : DIFIERE  (22933016d8c0 vs 253ee98cdf7c) -> dedup NO dispara -> DID NOT RAISE (flake)
MISMO archivo (fix)      : IDENTICO (22933016d8c0)                  -> determinista, siempre dispara
```

`_crear_bbva` (openpyxl) embebe `now()` en `docProps/core.xml` + entradas del zip → dos escrituras en
segundos distintos = bytes distintos = sha256 distinto → el dedup F-02 (sha256 de bytes) no dispara.

## 2. Diff — SOLO el test (service.py intacto)

```
$ git diff --stat origin/main...HEAD
 backend/tests/test_carga.py | 24 ++++++++++++++++++++----
 1 file changed, 20 insertions(+), 4 deletions(-)

$ git diff origin/main -- backend/app/cargas/service.py
 (vacío — service.py idéntico a main; linearizable revertido, majority de FIX-I intacto)
```

Cambio: `_procesar_s3(..., crear=True)`; el test de dedup llama la 2ª vez con `crear=False` (reprocesa
el MISMO archivo byte a byte). Determinista; preserva la semántica de F-02.

## 3. Regresión + lint

```
$ cd backend && python -m pytest -q
910 passed, 95 skipped, 0 fallos   (mongomock; los @requires_real_mongo corren en backend-real-mongo)
$ python -m pytest tests/test_carga.py -q
6 passed, 18 skipped               (18 real-mongo skip local)
$ python -m ruff check tests/test_carga.py         → All checks passed!
$ python -m ruff format --check tests/test_carga.py → already formatted
$ grep -rn "app.alegra.com/api/r1" | "journal-entries" | "estado.*pending" (cargas) → 0/0/0
```

## 4. Método (systematic-debugging, esta vez completo)

- **Fase 1 (causa raíz):** leí `_crear_bbva`/`_hash_archivo`, **reproduje** el mecanismo (§1) — no
  conjetura. Descarté mi hipótesis previa (majority stale) como imposible en RS 1 nodo + w:majority +
  awaits secuenciales (lo confirmó Kimi en FIX-I2-I).
- **Fase 3/4:** fix mínimo en el test (byte-identidad), `linearizable` revertido (placebo). Validación
  por CI `backend-real-mongo`, ahora **determinista** (no depende del reloj).
- Lección registrada: la causa raíz se demuestra o no se toca.
