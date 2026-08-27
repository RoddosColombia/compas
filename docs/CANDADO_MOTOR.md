# CANDADO_MOTOR.md — el candado del motor de proyección

| | |
|---|---|
| **Método** | COMPAS 2.0, Fase 0 (crítico) · deliverable F0-2 |
| **Fecha** | 2026-08-27 |
| **Anti-principio que protege** | Fundacional §4: *«No tocar el motor golden-master. Ningún cambio a la paridad de 176 meses sin gate explícito.»* |
| **Gate que realiza** | Fundacional §5: *«Golden-master del motor en CI — verde obligatorio en todo PR que toque proyección.»* |

## El problema

El motor `proyectar()` es verificable **porque su salida está clavada al peso** contra el
artefacto de referencia (`Dashboard_Artefacto.jsx`). Esa paridad es el activo más frágil
del sistema: un cambio silencioso en `backend/app/proyeccion/motor.py` que altere un
número invalida todas las decisiones de caja **sin que nadie lo note**. El riesgo tiene
**dos caras**:

1. **Deriva del motor** — alguien cambia el cálculo y la salida ya no reproduce el modelo.
2. **Manipulación de la golden** — alguien «arregla» el test regenerando
   `golden_simular.json` para que calce con el motor cambiado. El test pasaría, pero la
   paridad se habría movido a escondidas.

Un candado creíble tiene que cerrar **las dos**.

## Lo que ya existe (no partimos de cero)

- **`backend/tests/test_golden_master.py`** — compara `proyectar()` contra la GOLDEN
  campo por campo, 176 meses (`test_golden_master_paridad_por_mes`) + KPIs
  (`test_golden_master_kpis`). Tolerancia `TOL = 2 COP` (float JS vs Decimal). Dos
  divergencias intencionales están documentadas y aisladas en el propio test.
- **`backend/tests/golden/golden_simular.json`** — la GOLDEN, salida real de `simular()`
  del artefacto.
- **`backend/tests/golden/gen_golden.mjs`** — regenera la GOLDEN corriendo el JSX
  verbatim en Node (para cuando el artefacto de referencia cambie *a propósito*).
- Hoy este test corre **dentro** del job `backend` (`pytest -q`), así que ya falla ante
  deriva. Pero **no es un check nombrado ni requerido**, y **no hay guardia anti-manipulación**.

## La propuesta — tres piezas

### 1. Un check dedicado y nombrado: `golden-master`
Un job de CI que corre **solo** ese test, rápido y con nombre inconfundible, para que:
- un fallo diga «rompiste la paridad del motor», no «falló un test entre cientos»;
- se pueda exigir como **required status check** en la protección de rama.

```yaml
  # ── CANDADO DEL MOTOR (Fundacional §5) — paridad de 176 meses de proyectar() ──
  # Corre solo el golden-master, con nombre propio, para exigirlo como required check.
  golden-master:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -r requirements-dev.txt
      - name: golden-master (paridad del motor, 176 meses)
        run: pytest tests/test_golden_master.py -q
```

### 2. La guardia anti-manipulación: `motor-parity-guard`
Si un PR toca `backend/app/proyeccion/**` **o** modifica la GOLDEN
(`backend/tests/golden/golden_simular.json`), el PR **debe** llevar la etiqueta
`motor-parity-reviewed` (que solo pone el CEO/aprobador tras revisar el diff de paridad).
Sin la etiqueta, el job **falla**. Así, cambiar el motor o su golden exige un acto
explícito y trazable — el «gate explícito» del anti-principio.

```yaml
  # ── GUARDIA DE PARIDAD — cambiar el motor o su golden exige gate explícito ──
  motor-parity-guard:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
      - name: exigir etiqueta si el PR toca el motor o la golden
        env:
          LABELS: ${{ join(github.event.pull_request.labels.*.name, ',') }}
          BASE: ${{ github.event.pull_request.base.sha }}
          HEAD: ${{ github.event.pull_request.head.sha }}
        run: |
          CHANGED="$(git diff --name-only "$BASE" "$HEAD")"
          echo "$CHANGED"
          if echo "$CHANGED" | grep -Eq '^backend/app/proyeccion/|^backend/tests/golden/golden_simular\.json$'; then
            if echo ",$LABELS," | grep -q ',motor-parity-reviewed,'; then
              echo "OK: PR toca el motor/golden y trae la etiqueta motor-parity-reviewed."
            else
              echo "::error::Este PR toca backend/app/proyeccion/ o la golden. Exige revisar el diff de paridad y aplicar la etiqueta 'motor-parity-reviewed' (gate del CEO). Anti-principio Fundacional §4."
              exit 1
            fi
          else
            echo "OK: el PR no toca el motor ni la golden."
          fi
```

> Excepción legítima de la GOLDEN: cuando el artefacto de referencia cambie **a
> propósito**, se regenera con `gen_golden.mjs`, se revisa el diff numérico y se aplica
> la etiqueta. El candado no impide evolucionar el modelo; **obliga a que sea un acto
> consciente y aprobado**, nunca un efecto colateral.

### 3. La regla (protección de rama — paso manual del CEO en GitHub)
En *Settings → Branches → main → Require status checks to pass*, marcar como
**required**: `golden-master` y `motor-parity-guard` (junto a los ya existentes
`backend`, `frontend`, `gitleaks`, `pip-audit`). Esto es lo único que **no** vive en el
repo; queda como acción del CEO.

## Estado de aplicación

- Piezas **1 y 2** se agregan a `.github/workflows/ci.yml` en este mismo PR (aditivas; no
  tocan `motor.py` ni ningún job existente).
- Pieza **3** (marcar los checks como *required*) es el paso manual del CEO en la config
  de GitHub — no automatizable desde el repo.
- Verificación: el golden-master ya corre verde hoy (suite backend). El job dedicado solo
  lo aísla y lo nombra.
