# CR-WAVA — Dinero en tránsito (Wava) en el cierre y la apertura de mes

**Sprint:** posterior a E1 (toca el cierre certificado) · **Fecha:** 2026-08-01
**Solicita/aprueba:** Andrés San Juan (CEO) · **Ejecuta:** Claude Code
**Estado:** aprobado por el CEO (GO a los tres puntos, 2026-08-01); **construcción DESPUÉS de E1**.
Gate obligatorio: auditoría adversarial Kimi (toca lógica certificada del cierre); el paquete puede
viajar junto al de E1.

> **Nota de gobierno (M-3):** el *registro único de CR* aún no existe. Este CR se identifica por
> contenido (`CR-WAVA`), siguiendo la convención `CR-<nombre>` de `CR-E2-COMPUERTA`. **No abre una
> serie numérica.** Reconciliar en el registro único cuando se cree.

## Motivo

El dinero de Wava (pasarela de recaudo) **siempre llega a los bancos**, pero por tiempos de
*settlement* al cierre de mes queda plata recaudada que **aún no aterrizó en el banco**. Hoy la caja
del ciclo = **solo bancos** (`R_M` = Σ `saldos_banco` reportados; la caja inicial del mes siguiente se
ancla a `R_M`). Ese recaudo en tránsito no aparece en la caja de cierre → la caja final del mes queda
**subestimada** en el monto en tránsito.

El CEO necesita una opción **solo en el cierre y la apertura** para declarar ese tránsito, verlo como
una línea aparte, y que la llegada del depósito a inicios del mes siguiente **no se cuente dos veces**.

## Diseño autorizado — Opción B (capa aditiva declarada)

Descartada la Opción A (cuenta virtual con transacciones): obligaría a meter una "cuenta" al enum
`Banco` y a inventar la pata contraria del asiento sobre una sola línea de extracto (partida doble en
un sistema de partida simple) → viola regla 7 / R5 y rompe la conciliación `R_M/C_M`.

**Opción B — el tránsito es una capa paralela a la caja bancaria, nunca dentro de un banco:**

1. **Campo declarado en el cierre.** `MesControl` gana `transito_wava: Money = 0` (aditivo; migración
   idempotente deja los meses existentes en `0`). Se captura en `confirmar_cierre` (paso 2 del cierre),
   lo declara el CEO. **No entra** a `saldos_banco`, ni a `saldo_inicial_caja`, ni al *Ajuste de
   conciliación*.
2. **Dos líneas nombradas (R5).** Caja final del mes = **Bancos `R_M` · En tránsito Wava `Y` · Caja
   total `R_M + Y`**. Nunca sumado dentro de un banco. Caja inicial del mes nuevo = ancla bancaria
   (`saldo_inicial = R_M`, sin cambios) **+ tránsito heredado `Y`**, también en dos líneas.
3. **Rubro de sistema dedicado** `Tránsito Wava mes anterior` (`es_sistema=True`, `tipo_flujo=INGRESO`),
   sembrado por migración, en un **grupo NO-ingreso** para quedar **fuera del recaudo**. Los depósitos
   Wava que aterrizan en el banco a inicios del mes se clasifican contra este rubro (regla de
   clasificación dedicada o clasificación manual).
4. **Tránsito remanente = DERIVADO (no saldo mutable).** En un mes con tránsito heredado `Y`:
   `remanente = Y − Σ(tx con rubro «Tránsito Wava mes anterior» en el mes)`. Compute-only.
5. **Aviso al siguiente cierre.** Si al cerrar queda `remanente > 0`: *"declaraste $Y en tránsito y solo
   llegaron $W"*.

### La trampa que se cierra (invariante del punto 4)

El depósito Wava que llega al banco es **un ingreso bancario real** (viene del extracto) → la
conciliación bancaria **cuadra sola** (el saldo reportado subió, el libro tiene el movimiento). Al
clasificarlo contra `Tránsito Wava mes anterior`:

- **Banco `+W`** (entra a `caja_libro` / lo refleja `R_{M}`) — dinero ahora en el banco. ✓
- **Tránsito `−W`** (un tx más de Tránsito-Wava ⇒ `remanente` baja `W`). ✓
- **Caja total: `+W − W` = igual.** ✓
- **Recaudo del mes: sin cambio** (el rubro está fuera del grupo de ingresos). ✓

**Test obligatorio:** la llegada del depósito **NO infla el recaudo del mes** ni cambia la **caja
total** (banco sube, tránsito baja, total igual). TDD, rojo→verde.

## Qué toca de lógica certificada (R6) — y qué NO

- **La matemática de conciliación / re-ancla / *Ajuste de conciliación* / saga O1 / reapertura NO
  cambia.** `R_M`, `C_M = saldo_inicial + Σ signo(tx)`, `diferencia`, el ajuste día-1 en M+1 y el LIFO
  quedan intactos. El tránsito es una capa paralela que no entra a ninguno de esos cálculos.
- **Sí toca la *superficie* certificada del cierre:** `confirmar_cierre` recibe un input nuevo
  (`transito_wava`), lo persiste en `MesControl(M)` y lo agrega al metadata de `mes.cerrado`; el
  `request_hash` de la Idempotency-Key del endpoint `POST /meses/{mes}/cierre/confirmar` **debe incluir
  `transito_wava`** (para que un reenvío con otro monto se detecte). Por eso **este CR va con gate
  Kimi**.

## Auditoría — evento

**Recomendado: plegar en `mes.cerrado`.** El monto declarado queda auditado **con autor** dentro del
`mes.cerrado` (que ya lleva `usuario_id`). El catálogo **no crece** → R3 satisfecha sin CR de eventos.
La clasificación de los depósitos usa el `transaccion.clasificada` existente; el rubro de sistema se
siembra por migración (sin evento).

**Alternativa para que Kimi opine en el gate:** un evento dedicado `transito.declarado` (catálogo
+1 → CR de eventos) si el auditor considera que el tránsito merece rastro forense propio, separado del
cierre. El CEO comparte la recomendación de plegarlo; se deja la alternativa planteada.

## Precisión de transición — el cierre de julio 2026

Julio 2026 **se cierra SIN esta funcionalidad** (documentado como ajuste conocido, ver
`docs/NOTA_Transito_Wava_Julio_2026.md`). Como **julio NO contó el tránsito**, los depósitos Wava que
lleguen al banco a inicios de **agosto SÍ son ingreso de agosto, esta única vez** (reconocimiento
tardío, **no** doble conteo). **La regla "clasificar contra el tránsito" rige desde el PRIMER cierre
que declare tránsito (agosto en adelante).** Que nadie clasifique los depósitos de agosto-por-julio
contra un tránsito inexistente. La implementación debe hacer inocuo el caso `transito_heredado = 0`
(sin tránsito declarado ⇒ no hay nada contra qué clasificar y no se dispara ningún aviso).

## Impacto en E1 (anotar en el PASO 0 de E1)

El futuro rubro de sistema **`Tránsito Wava mes anterior` se EXCLUYE deliberadamente del mapeo
rubro→concepto** de E1: **no es ingreso ni gasto** y **no debe quedar como "sin mapear"** disparando el
aviso permanente de conceptos sin clasificar. El mapeo de E1 debe contemplar esta exclusión explícita
(lista de rubros de sistema neutros, junto con `Ajuste de conciliación`).

## Calendario

Construcción **DESPUÉS del gate de E1** (mañana domingo es E1 completo, no se comparte). Cero código de
Wava antes de ese gate. Este CR queda escrito hoy para que el paquete Kimi esté listo para viajar con
el de E1.

## Alcance de implementación (estimado ~2–4 días + ronda Kimi)

Backend: campo `transito_wava` + migración idempotente · `confirmar_cierre` (input + persistencia +
metadata + hash de idempotencia) · rubro de sistema sembrado + exclusión del recaudo · remanente
derivado expuesto en las respuestas de caja · aviso al cierre · **test obligatorio de la trampa** +
tests de cierre/apertura/arrastre. Frontend: campo "Dinero en tránsito (Wava)" en el confirmar ·
dos líneas de caja (cierre, apertura, Control, Dashboards) · aviso del remanente. `motor.py` cero
diffs; compuerta IVA apagada (no se toca).

## Reversa

El campo por defecto en `0` y el rubro de sistema son inertes si nadie declara tránsito. Revertir el
commit restaura `confirmar_cierre` original; los meses con `transito_wava = 0` quedan idénticos al
comportamiento previo.
