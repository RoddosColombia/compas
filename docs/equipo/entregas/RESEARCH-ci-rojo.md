# RESEARCH - CI en rojo permanente

Autor: Jose (Researcher 1) - 2026-09-15
Alcance: diagnostico de los 3 checks que fallan siempre en el CI de este repositorio. Sin arreglos, sin PR, sin tocar el motor de proyeccion.

## Escalacion, antes que todo lo demas

Existe una memoria del proyecto llamada `ci-actions-billing-bloqueado` que se esta usando (o se puede usar) para explicar por que el CI esta en rojo. Esa memoria describe un incidente REAL y ya resuelto (bloqueo de facturacion de GitHub Actions, dos episodios, el segundo cerrado el 2026-08-17), con un sintoma muy especifico y verificable: los jobs fallaban en 2 a 3 segundos con una anotacion textual de GitHub sobre pagos fallidos, sin ejecutar ningun paso real.

Eso no es lo que esta pasando hoy. Verificado con evidencia directa:

- Los runs actuales duran entre 5 y 15 minutos, ejecutan todos los pasos reales (install, lint, build, pytest), y producen logs completos con errores de codigo concretos (ver los 3 bloques abajo).
- En el mismo run fallan 2 o 3 jobs mientras 5 o 6 pasan completos (`golden-master`, `gitleaks`, `pip-audit`, `runtime-imports`, `backend-real-mongo`, `motor-parity-guard`). Si la cuota de minutos estuviera agotada o el pago fallara, ningun job arrancaria, no unos si y otros no.

Usar esa memoria para explicar el rojo actual es un error: describe una causa raiz distinta, de un episodio ya cerrado, que no aplica a lo que se ve hoy.

Ademas, la propia memoria trae una afirmacion tecnica que la evidencia de hoy contradice: dice, citando textual, *"Required check: IMPOSIBLE en plan Free con repo privado (403 en branch protection Y en rulesets, probado 2026-08-17)"*. Verificacion directa hoy:

```
gh api orgs/RoddosColombia --jq '{plan: .plan.name}'
  → {"plan":"free"}
gh api repos/RoddosColombia/compas/branches/main/protection --jq '.required_status_checks.contexts'
  → ["backend","backend-real-mongo","frontend","runtime-imports","pip-audit","gitleaks","golden-master","motor-parity-guard"]
```

La organizacion sigue en plan Free (1 asiento) y sin embargo la proteccion de rama SI tiene 8 checks obligatorios configurados y funcionando. Esto contradice directamente lo que la memoria registro como probado el 2026-08-17. No se por que cambio (pudo cambiar una politica de GitHub, o la prueba de entonces estuvo mal hecha, o algo mas), y no lo voy a especular. Dejo esto marcado para que el arquitecto lo revise y decida si corrige o retira esa memoria.

## Contexto

La proteccion de main exige 8 checks (`backend`, `backend-real-mongo`, `frontend`, `runtime-imports`, `pip-audit`, `gitleaks`, `golden-master`, `motor-parity-guard`) con `enforce_admins: false`. Un noveno check, `reglas inviolables (CLAUDE.md)` (semgrep), corre en cada PR pero NO esta en la lista de obligatorios.

De los 8 obligatorios, 6 pasan siempre (`backend-real-mongo`, `runtime-imports`, `pip-audit`, `gitleaks`, `golden-master`, `motor-parity-guard`). Dos fallan siempre: `backend` y `frontend`. El noveno check no obligatorio (`reglas inviolables`) tambien falla siempre.

## Resumen ordenado por facilidad de arreglo

| Orden | Check | Tipo de falla | Dificultad | Desbloquea |
|---|---|---|---|---|
| 1 | `reglas inviolables (CLAUDE.md)` (semgrep) | Config del propio workflow (regla con sintaxis invalida) + 1 falso positivo no excluido | Trivial | Un check completo, 100% roto desde el dia que se creo, y el ruido de "todo en rojo" en cada PR |
| 2 | `frontend` | Codigo no conforme al formateador/linter (Biome), acumulado sin arreglar | Trivial a moderado (mecanico, sin logica de negocio) | Un check obligatorio completo |
| 3 | `backend` | Un test especifico de la proyeccion (particion de un modelo en dos planes) falla de forma determinista | Hay que entender algo primero, toca el motor/PLAN-52 | Un check obligatorio, pero exige a alguien que entienda la particion de planes, no a mi |

---

## 1. `reglas inviolables (CLAUDE.md)` (semgrep) - el mas facil

### 1. Error concreto

Log real (`gh run view --log-failed`, job del workflow G-SEMGREP para el PR #166):

```
semgrep-core rule validation failed (PatternParseError)
...
[ERROR] Rule parse error in rule ruta-sin-auth:
 Invalid pattern for Python: Stdlib.Parsing.Parse_error
----- pattern -----
@$ROUTER.$METHOD(...)
async def $F(..., ...: ... = Depends(require_permission(...)), ...):
  ...
----- end pattern -----
```

Y, en el mismo run, un finding real que tambien bloquea (con `--strict`, cualquiera de los dos ya tumba el job):

```
backend/app/cfo/config.py
   dinero-nunca-float
       Dinero SIEMPRE es Decimal, nunca float (CLAUDE.md regla 1)...
        33: return float(os.environ.get("CFO_TIMEOUT_S", "60"))
Ran 3 rules on 196 files: 1 finding.
##[error]Process completed with exit code 1.
```

### 2. Desde cuando falla

Desde siempre. `gh run list --workflow=semgrep.yml --limit 100` devuelve **78 de 78 runs en failure**, sin una sola excepcion en todo el historial retenido. El workflow y el archivo de reglas (`.github/workflows/semgrep.yml`, `.semgrep.yml`) se crearon en un unico commit y nunca se volvieron a tocar:

```
git log --oneline -- .semgrep.yml
  ee29b4b feat(gates): G-SEMGREP + G-TRIVY workflows + G-SEC doc + G-GM required - PR-1 de 2
git show -s --format="%ci" ee29b4b
  2026-08-31 09:12:54 -0500
```

Este check nacio roto el 2026-08-31 y nadie lo volvio a mirar desde entonces (nunca fue obligatorio, asi que nunca bloqueo un merge, asi que nadie tuvo que arreglarlo).

### 3. Tipo de falla

Dos causas independientes, ambas de **configuracion del propio workflow** (no es codigo de la app roto, no es entorno, no es dependencia):

- La regla `ruta-sin-auth` en `.semgrep.yml` (lineas 106 a 113) usa un patron `pattern-not` con un argumento tipado y con valor por defecto (`...: ... = Depends(...)`) que el motor de Semgrep instalado no puede parsear. Con `--strict`, un error de parseo de UNA regla hace fallar la corrida completa, aunque las otras 2 reglas esten bien.
- La regla `dinero-nunca-float` excluye explicitamente `backend/app/cfo/telegram/cliente.py` como caso legitimo de `float()` para timeout de red (no dinero), pero `backend/app/cfo/config.py:33` hace exactamente lo mismo (`CFO_TIMEOUT_S`, un timeout, no un monto) y no esta en la lista de excepciones. Esto es casi con certeza un falso positivo por una exclusion incompleta, no una violacion real de la regla 1 de CLAUDE.md.

### 4. Dificultad

**Trivial.** Sugerencia concreta para quien lo arregle (no lo aplico yo):

- En `dinero-nunca-float`, agregar `backend/app/cfo/config.py` a la lista `paths.exclude`, igual que ya esta `cliente.py`.
- En `ruta-sin-auth`, simplificar el `pattern-not` para que no dependa de un argumento tipado con default dentro del patron (por ejemplo, separar la deteccion de "tiene Depends(require_permission(...))" de la anotacion de tipo), o consultar la documentacion actual de sintaxis de Semgrep para la forma correcta de expresar un parametro opcional en un pattern-not.

### 5. Reproducible localmente

Si. Con `pip install "semgrep>=1.90,<2"` y `semgrep --config .semgrep.yml --error --strict --disable-version-check` se reproduce el mismo `PatternParseError` y el mismo finding, exactamente como en CI (no lo corri yo mismo en esta maquina porque instalar semgrep no aportaba nada que el log de CI no mostrara ya completo, pero el comando esta documentado arriba en el propio workflow).

### 6. Lectura del workflow

`.github/workflows/semgrep.yml`: un solo job (`semgrep`, nombre visible `reglas inviolables (CLAUDE.md)`), instala `semgrep>=1.90,<2` y corre `semgrep --config .semgrep.yml --error --strict --disable-version-check` contra todo el repo. `.semgrep.yml` define 3 reglas (todas ERROR):

1. `dinero-nunca-float`: dinero es Decimal, nunca `float()`, con 2 exclusiones ya documentadas (tests, y `cliente.py` por timeout de red).
2. `audit-log-append-only`: nada de `.update_*()`/`.delete_*()` sobre `audit_log` (regla 4 de CLAUDE.md).
3. `ruta-sin-auth`: toda ruta FastAPI en `router.py` debe declarar `Depends(require_permission(...))`, con `backend/app/auth/router.py` excluido (login/refresh/logout no pueden exigir estar autenticado).

Las reglas 1 y 2 corren bien (no dan error de parseo); solo la regla 3 tiene el patron invalido.

---

## 2. `frontend`

### 1. Error concreto

`npm run lint` corre `biome check .` y falla con **31 errores**. Categorias reales encontradas (nombre de regla de Biome), verificado en CI y reproducido localmente:

- `lint/style/useTemplate` (6 casos)
- `lint/suspicious/noArrayIndexKey` (4 casos, por ejemplo `src/components/fabs/FabsPanel.tsx:88` y `:417`)
- `lint/style/noNonNullAssertion` (1 caso)
- `lint/correctness/useExhaustiveDependencies` (1 caso)
- Formato/orden de imports (Biome `format` y `organizeImports`) en varios archivos, entre ellos `src/components/decisiones/VallesCard.tsx`, `src/components/fabs/FabsPanel.tsx`, `src/components/caja/ReporteCajaCard.test.tsx`, `src/components/charts/ComposicionFlujoRV2.test.tsx`, `src/components/charts/CurvaCajaRV2.test.tsx`, `src/components/fabs/FabsPanel.test.tsx`.

El job entero se detiene ahi: `ci.yml` corre `npm run lint` ANTES de `npm run build` y de `npm run test`, y GitHub Actions no sigue a un paso siguiente si el anterior falla. Es decir, ni `build` ni `test` llegan a correr en CI para este job. Esto importa para el punto 5.

### 2. Desde cuando falla

Bisecte el historial de runs del workflow CI en la rama `main` comparando el job `frontend` de a un run a la vez (`gh run view <id> --json jobs`). Resultado exacto:

- Ultimo run con `frontend: success`: `33347853856` (2026-08-31 01:31:54, "Merge pull request #125 from RoddosColombia/fix/test-db-paquete-vigilante"), commit `4e9ecd7`.
- Primer run con `frontend: failure`: `33347869957` (2026-08-31 01:32:13, "Merge pull request #119 from RoddosColombia/feat/rf-f7-reparto-por-rubro"), commit `62d24d5`.

El diff entre esos dos commits toca exactamente `frontend/src/components/decisiones/VallesCard.tsx` (111 lineas), y ese es uno de los archivos que Biome sigue marcando HOY, 15 dias despues:

```
git log --oneline 4e9ecd7..62d24d5
  62d24d5 Merge pull request #119 from RoddosColombia/feat/rf-f7-reparto-por-rubro
  c2be91b feat(rf-f7): recomendaciones por impacto - reparto del recorte por rubro (motor corrido al reves)
  ...
git diff --stat 4e9ecd7 62d24d5 -- frontend/
  frontend/src/components/decisiones/VallesCard.tsx | 111 ++++++++++++++++-----
```

El commit `c2be91b` (PR #119, 2026-08-31) agrego codigo a `VallesCard.tsx` sin correr el formateador antes de commitear. `FabsPanel.tsx` se agrego mas tarde ese mismo dia (feature de chat FABS) y arrastra el mismo problema. Desde entonces, cada archivo nuevo que alguien no formatea antes de commitear se suma a la lista, porque el check nunca bloqueo nada (no hay reviews obligatorias y el override de administrador siempre estuvo disponible).

### 3. Tipo de falla

**Codigo no conforme al formateador/linter, acumulado.** No es un bug funcional: confirmado en el punto 5 que el build y los tests pasan limpios. No encaja del todo en ninguna de las 5 categorias que me dieron (no es "codigo roto de verdad" en el sentido de comportamiento incorrecto, no es test desactualizado, no es entorno, no es config del workflow, no es dependencia); la mas cercana es simplemente deuda de formato nunca pagada porque el gate nunca freno un merge.

### 4. Dificultad

**Trivial a moderado.** `biome check --fix --unsafe` corrige automaticamente la mayoria (el log dice literal "Skipped 3 suggested fixes... use biome check --fix --unsafe"); quedan 3 fixes marcados como "unsafe" que alguien debe revisar a mano antes de aplicarlos (son reordenamientos de JSX/imports, no cambios de logica), mas 1 import fuera de orden en `FabsPanel.tsx`. Nada de esto toca logica de negocio.

### 5. Reproducible localmente

**Si, en su totalidad y de forma limpia:**

- `npm ci` + `npm run lint` reproduce exactamente "Found 31 errores", mismos archivos.
- `npm run build` (que corre `tsc -b && vite build`) **pasa limpio, sin errores de tipos**, build completo en 3 segundos. El motor de tipos de TypeScript no tiene ningun problema.
- `npm run test -- --run` (Vitest) **pasa completo: 408 de 408 tests, 63 de 63 archivos**.

Conclusion importante: el unico problema real de `frontend` es el linter/formateador. El build y los tests, que es lo que de verdad protege al producto, estan sanos.

Nota de entorno: corri esto con Node 24.14.0 y npm 11.9.0 localmente; CI usa Node 22 (`setup-node` con `node-version: "22"`). No encontre motivo para pensar que la version de Node cambia el resultado de Biome/tsc/Vitest aqui, pero lo marco por transparencia (no lo verifique con Node 22 exacto).

### 6. Lectura del workflow

`ci.yml`, job `frontend`: `npm ci` (usa `package-lock.json`) -> `npm run lint` -> `npm run build` -> `npm run test`, en ese orden, sin `continue-on-error`. `package.json` define `"lint"` como el comando de Biome y `"build"` como `tsc -b && vite build` (memoria del proyecto `frontend-verificar-npm-run-build` ya documentaba que `tsc -b` tambien tipa los tests; confirmado, el build corrio sobre toda la base incluidos los `.test.tsx`).

---

## 3. `backend`

### 1. Error concreto

Un solo test falla, siempre el mismo, con el mismo mensaje exacto:

```
FAILED tests/test_modelos_planes.py::test_proyeccion_con_dos_planes_particion_no_inventa_plata
AssertionError: recaudo se desvia mas de 0.5%: base 171587200.00 vs dividido 169738200.00
assert Decimal('1849000.00') <= (Decimal('171587200.00') * Decimal('0.005'))
1 failed, 1592 passed, 102 skipped
```

La desviacion real es 1.08% (1.849.000 / 171.587.200), mas del doble de la tolerancia de 0.5% que el propio test declara aceptable.

### 2. Desde cuando falla, y aviso importante

Aca me detengo antes de lo que hubiera hecho en un check normal, porque este test toca directamente la proyeccion (PLAN-52, particion de un modelo en dos planes) y la instruccion que recibi es no meterme mas alla de reportar cuando una falla involucra al motor.

Lo que si pude establecer con evidencia, sin tocar ni ejecutar nada del lado del motor mas alla de correr el test tal cual esta:

- El ultimo run de CI donde el job `backend` paso **completo**, con los 3 pasos (`ruff check`, `ruff format --check`, `pytest`) en verde, fue el `33327782903` (2026-08-30 18:20:23, commit `33398c7`): **1397 tests pasaron, 0 fallaron**.
- Justo despues, entre el 2026-08-30 19:37 y el 2026-09-04 00:38, el job `backend` fallo en el paso `ruff format --check` (3 archivos de test sin formatear), lo que significa que `pytest` **no llego a correr** durante esa ventana (GitHub Actions no corre el paso siguiente si el anterior falla). Es decir, no hay evidencia de CI de si este test especifico pasaba o fallaba en esos dias.
- El primer run donde `ruff format` volvio a pasar y `pytest` volvio a ejecutarse fue el `33822578684` (2026-09-04 00:38, commit `8c64d96`, "chore(lint): ruff check --fix + format"): ahi aparece la falla, con el **mismo numero exacto** (171587200.00 vs 169738200.00) que veo hoy, 2026-09-15, 11 dias y decenas de commits despues.
- Reproduje el test en aislamiento total en mi maquina (`python -m pytest tests/test_modelos_planes.py -q`, corriendo solo ese archivo, sin el resto de la suite): falla igual, mismo numero exacto. Esto descarta que sea un problema de orden de ejecucion o de contaminacion entre tests (ademas confirme que el fixture de Mongo simulado es por-test, no compartido entre tests).
- Revise el diff completo entre el ultimo commit bueno conocido (`33398c7`) y el primer commit donde se confirmo la falla (`8c64d96`): son 5 commits que tocan `backend/app/proyeccion/` (agregan `agregacion.py`, `reparto.py`, cambios a `router.py` y `service.py` por features RF-F7/RF-F8/RF-F9/RF-F10/RV-V2), mas 2 commits que tocan `backend/app/modelos_moto/service.py` (6 lineas, una funcion nueva sin relacion) y `backend/app/domain/parametros_proyeccion.py` (1 linea, tope de horizonte 180 a 240). Ninguno de esos diffs, buscando por las palabras `plan`, `peso`, `mix`, `recaudo`, toca de forma obvia la logica de particion entre plan1/plan2. El archivo `motor.py` (el motor certificado propiamente dicho) **no cambio en absoluto** en esa ventana.

**No pude aislar el commit exacto sin meterme mas a fondo en el codigo de la proyeccion/particion de planes, y ahi es donde me detengo, tal como se me pidio.** Lo que si puedo afirmar con evidencia solida: el test paso el 2026-08-30, esta roto de forma 100% determinista y reproducible desde por lo menos el 2026-09-04, y el motor certificado (`motor.py`, protegido por `golden-master`) no se toco en esa ventana, asi que si hay una causa raiz de codigo, esta en la capa de servicio/particion de planes alrededor del motor, no en el motor mismo.

### 3. Tipo de falla

No lo clasifico con certeza porque eso exige entender la logica de particion, que es justo lo que se me pidio no hacer. Lo que la evidencia SI permite descartar: no es flaky (reproducible 100% de las veces, en aislamiento, en 3 fechas distintas con el mismo numero exacto), no es un problema de entorno (corre igual en CI que en mi maquina), y no es una dependencia rota (nada en el `pip-audit` ni en los cambios de `requirements.txt` de esa ventana se relaciona). Queda entre "codigo roto de verdad" (una regresion real en como se reparte el recaudo entre dos planes) o "test desactualizado" (la tolerancia de 0.5% ya no aplica al comportamiento actual, documentado, del motor). Distinguir entre esas dos lecturas es exactamente el trabajo que le toca a quien entienda la particion, no a mi.

### 4. Dificultad

**"Hay que entender algo primero."** Especificamente: como el motor certificado reparte altas semanales cuando un modelo se divide en dos planes con distinto peso, y si la tolerancia de 0.5% mensual del test sigue siendo la correcta dado el comportamiento actual (documentado y con golden-master intacto) del motor.

### 5. Reproducible localmente

Si, en aislamiento total, con el mismo numero exacto. Detalle de entorno: corri con Python 3.14.3 local (CI usa 3.12); no encontre motivo para pensar que la version de Python cambia un calculo de Decimal determinista, pero lo marco por transparencia, igual que con Node en el bloque de frontend.

### 6. Lectura del workflow

`ci.yml`, job `backend`: `pip install -r requirements-dev.txt` -> `ruff check .` -> `ruff format --check .` -> `pytest -q --cov=app --cov-report=term-missing`, en ese orden, sin `continue-on-error`. Mismo patron que `frontend`: un paso temprano que falla oculta lo que pasa en los pasos siguientes, y eso fue exactamente lo que paso aca entre el 30 de agosto y el 4 de septiembre con `ruff format`.

---

## Tabla resumen

| Check | Paso que falla | Desde cuando (evidencia) | Reproducible local | Toca el motor |
|---|---|---|---|---|
| `reglas inviolables (CLAUDE.md)` | `semgrep --config .semgrep.yml` | Desde el commit que lo creo, `ee29b4b`, 2026-08-31. 78/78 runs en failure. | Si (comando documentado en el propio workflow) | No |
| `frontend` | `npm run lint` (Biome) | Desde el commit `c2be91b` (PR #119), 2026-08-31 01:32. Build y tests, sanos. | Si, limpio | No |
| `backend` | `pytest` (1 de 1593 tests) | Confirmado roto desde 2026-09-04 (posiblemente antes, pero enmascarado por `ruff format` hasta esa fecha). `motor.py` no cambio en la ventana. | Si, en aislamiento total | Si (particion de planes, capa alrededor del motor) |

## Gaps

1. **Commit exacto que rompio el test de backend.** Acote la ventana a 5 a 7 commits (los que tocan `backend/app/proyeccion/`, `backend/app/modelos_moto/service.py` y `backend/app/domain/parametros_proyeccion.py` entre `33398c7` y `8c64d96`), pero no revise cada uno linea por linea porque eso exige entender la logica de particion, fuera de mi alcance en esta tarea. Un bisect real (correr el test en cada commit intermedio) lo cerraria; no lo hice porque implica ejecutar codigo del motor commit a commit, mas alla de lo que se me pidio.
2. **Por que `required_status_checks` funciona hoy en plan Free**, contradiciendo lo que la memoria `ci-actions-billing-bloqueado` registro como probado el 2026-08-17. No se si GitHub cambio esa politica, si la prueba de entonces estuvo mal hecha, o si algo mas cambio en la cuenta. Lo dejo para que el arquitecto lo revise contra el historial de facturacion/soporte de GitHub si hace falta.
3. **Efecto real de la diferencia de version de Node (22 en CI vs 24 aqui) y de Python (3.12 en CI vs 3.14 aqui).** No encontre motivo tecnico para sospechar que cambia algo de lo reportado, pero no corri la reproduccion exacta con las mismas versiones de CI.
4. **Los `.semgrep.yml` avisos de "Semgrepignore v2"** (rutas que semgrep advierte que van a interpretarse distinto "pronto") no los investigue a fondo; son warnings, no la causa del fallo actual, pero podrian doler en una futura actualizacion de semgrep si no se anclan las rutas con `/` inicial como sugiere el propio aviso.

## Related

- `.github/workflows/ci.yml`, `.github/workflows/semgrep.yml`, `.semgrep.yml` - los 3 workflows/config leidos completos para este dossier.
- `backend/tests/test_modelos_planes.py:314-354` - el test que falla en `backend`.
- `backend/app/cfo/config.py:33` - el falso positivo probable de `dinero-nunca-float`.
- Memoria `ci-actions-billing-bloqueado` - describe un incidente real y cerrado, no aplica al rojo actual (ver seccion de Escalacion).
- PR #166, run `34912575186` (CI) y `34912575047` (G-SEMGREP) - evidencia base de este dossier.
