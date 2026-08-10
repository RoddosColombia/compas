# CR-PTS6F — Cartera de apertura: refresco mensual de la serie de recaudo desde el LoanTape

**Sprint:** cola 6-puntos pre-FABS · **Fecha:** 2026-08-10
**Solicita/aprueba:** Andrés San Juan (CEO) · **Ejecuta:** Claude Code (terminal)
**Estado:** **BORRADOR — espera GO del CEO.** No se construye nada hasta el GO.
Gate obligatorio: auditoría adversarial Kimi (aunque el motor no cambia, la capa alimenta
la proyección de caja del norte — umbral mayo-2027). Capa **ADITIVA**: `motor.py` cero diffs.

> **Nota de gobierno (M-3):** el registro único de CR aún no existe. Este CR se identifica por
> contenido (`CR-PTS6F`), convención `CR-<nombre>`. No abre serie numérica. Reconciliar en el
> registro único cuando se cree. Relacionado con [[cartera_previa]], el [Contrato LoanTape
> SISMO-V3](CONTRATO-SISMO-V3-LOANTAPE.md) y la decisión CEO D6 (2026-08-10): *"mes a mes se
> cargará el comportamiento de cartera para ir actualizando parámetros como mora y default"*.

## Motivo (la causa raíz que quedó abierta en PTS6-A)

El motor de proyección suma **tres** cosas para el recaudo de crédito de un mes: las cohortes
**nuevas** que él simula desde `mes_inicio` + la **serie de la cartera previa**
(`cartera_previa_recaudo`, un tercer sumando). Esa serie es hoy un **snapshot CONGELADO** del
artefacto: los 111 créditos preexistentes, semanas `w1` (mié 2026-03-04) … `~w97`, extraídos una
vez a mano.

El hueco: el motor **no tiene estado de apertura de cartera**. Cuando `mes_inicio` = el mes en
curso (default del endpoint, `proyeccion/router.py`), **todo crédito colocado ANTES de ese mes
que no esté en la serie congelada desaparece** del recaudo. Tras sembrar la serie (PTS6-A),
agosto-2026 proyecta **~$127 M**; el golden honesto desde mayo da **~$142 M** para el mismo mes.
Esa diferencia (~$15 M) son **colocaciones reales de jul–ago 2026** que quedaron fuera: demasiado
nuevas para el snapshot congelado, anteriores a `mes_inicio` para la simulación.

A medida que pasan los meses el hueco **crece** (cada mes coloca créditos que el snapshot no
conoce). El snapshot congelado además **no refleja la mora/default reales** que se van observando.

## Qué se propone (capa aditiva, el motor no cambia)

**Regenerar la serie de la cartera de apertura desde el LoanTape, mes a mes**, en lugar de dejar
el snapshot congelado del artefacto:

1. **Fuente:** la colección `loantape_creditos` (contrato SISMO-V3 ya definido; carga semanal por
   crédito, con `cuota_semanal`, `plazo_semanas`, `cuotas_pagadas`, `fecha_desembolso`,
   `saldo_pendiente`, `dias_mora`, `estado`). Hoy la carga existe (`loantape/service.py`) y se usa
   solo para el aging; esta capa le da un segundo consumidor.

2. **Derivación de la serie** (código determinista, función pura sobre el corte más reciente):
   para cada crédito **vivo** a la `fecha_corte`, proyectar su **cronograma restante** semana a
   semana (`cuota_semanal` × semanas que faltan, desde la próxima cuota) y **sumar por semana
   global** (misma numeración `w` = miércoles desde 2026-03-04 que ya usa el motor). Resultado:
   la misma forma que `cartera_previa_recaudo` (`{semana_global, recaudo, n_activos}`), pero
   **viva** — cubre TODOS los créditos colocados hasta el corte, no solo los 111 originales.

3. **Refresco:** cada cierre de mes (cadencia mensual, D6), tras cargar el LoanTape del corte, se
   **regenera** la serie. Idempotente por `semana_global` (upsert). El CEO puede seguir corrigiendo
   a mano (se respeta su corrección, ver decisión Q1).

4. **Frontera anti-doble-conteo (la trampa que hay que cerrar):** la serie derivada cubre lo
   colocado **hasta el corte**; el motor simula lo colocado **desde `mes_inicio`**. Para que un
   crédito no se cuente dos veces, `mes_inicio` de la proyección debe alinearse a **(mes del corte
   + 1)**. Hoy `mes_inicio` = mes en curso y el corte del LoanTape es el último miércoles → la
   alineación es natural al cerrar el mes, pero **debe hacerse explícita y probada** (test de
   frontera: ningún crédito del LoanTape aparece también como cohorte simulada).

5. **Parámetros mora/default (D6):** del mismo LoanTape se recalculan `pct_mora`/`pct_default`
   observados por tramo de aging y se ofrecen como sugerencia para `parametros_proyeccion` (el CEO
   decide si adopta; no se auto-aplica).

## Decisiones que necesito del CEO (bloquean el diseño fino)

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| Q1 | ¿Dónde vive la serie viva? | (A) **refrescar** `cartera_previa_recaudo` (reusa el cableado del motor; una corrección manual del CEO se marca `origen='manual'` y NO se pisa) · (B) colección nueva `cartera_apertura` + nuevo sumando en el motor (más superficie, toca `motor.py`) | **(A)** — cero diffs de motor, un solo sumando |
| Q2 | ¿Las semanas FUTURAS de la serie van brutas o netas de mora? | (a) **brutas** (el motor aplica sus `pct_mora`/`default` encima, como hoy) · (b) **netas** de la mora observada por crédito | **(a)** — no duplica el haircut; el motor ya modela mora |
| Q3 | Cadencia del refresco | (a) **mensual** al cierre (alineada con la frontera `mes_inicio`) · (b) semanal (más fresco, pero desalinea la frontera intra-mes) | **(a)** — coincide con D6 y con el corte de `mes_inicio` |
| Q4 | Origen del LoanTape para v1 | (a) **carga manual** del archivo (ya existe el endpoint) · (b) conexión automática a SISMO-V3 | **(a)** para v1 (Liz sube el archivo); (b) queda para después |

## Garantías (lo que el CR promete al gate)

- **`motor.py` cero diffs** (regla motor-intocable): la capa solo **reescribe datos** de un tercer
  sumando que el motor ya consume. Golden-master intacto.
- **Idempotente y reversible:** regenerar dos veces = mismo resultado; el snapshot anterior queda
  versionado/fechado para poder volver.
- **Sin PII** (regla NORTE / Ley 1581): el LoanTape trae `cliente_id` OPACO; la serie derivada es
  agregada por semana (sin identificadores).
- **Persistente y administrable** (reglas NORTE/9): dato en Mongo, el CEO puede corregir.
- **TDD:** función de derivación pura con casos resueltos a mano; test de frontera anti-doble-conteo;
  test de que agosto-2026 sube de ~$127 M a ~$142 M (≈ golden) con un LoanTape de fixture.

## Alcance explícito (lo que NO hace)

- No toca el motor, el golden, ni la matemática certificada.
- No cambia la conciliación de caja ni el cierre.
- No auto-aplica los parámetros de mora/default (solo los sugiere).
- No construye la conexión automática a SISMO-V3 (v1 = carga manual).

## Plan de construcción (tras el GO + gate Kimi)

1. Función pura `serie_apertura_desde_loantape(corte)` → `[{semana_global, recaudo, n_activos}]` (TDD).
2. Job/servicio de refresco (mensual, en el Worker — regla 6) que la persiste (upsert idempotente).
3. Alineación explícita de `mes_inicio` a (corte + 1) + test de frontera.
4. Sugerencia de `pct_mora`/`pct_default` observados (informativa).
5. Evidencia: agosto ~$142 M; regresión verde; paquete Kimi.

Esfuerzo estimado: 3–4 días de técnico. Depende de que el LoanTape de PROD tenga datos (hoy
`loantape_creditos` está vacía — la primera carga la hace Liz con el archivo de SISMO-V3).
