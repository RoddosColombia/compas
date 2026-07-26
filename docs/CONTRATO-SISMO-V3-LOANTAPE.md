# Contrato de datos — SISMO-V3 -> COMPAS (LoanTape semanal)

**Versión:** 1.0 · **Fecha:** 2026-07-26 · **Decisión CEO:** SISMO-V3 es la fuente de
verdad de los pagos. COMPAS tendrá conexión con SISMO-V3 y, además, una carga (upload)
manual del mismo archivo. Este documento define QUÉ debe entregar SISMO-V3 cada semana.

## Para qué sirve

COMPAS construye, a partir de este archivo:

1. **Mora por tramo (aging):** la cartera morosa clasificada por días de atraso
   (al día / 1-30 / 31-60 / 61-90 / 90+), por monto y por número de créditos.
2. **Proyección de recaudo crédito a crédito:** con el cronograma restante de cada
   crédito, en vez del porcentaje de mora agregado que usa hoy el motor — mayor
   fidelidad para el norte predictivo (umbral de caja, objetivos de venta).
3. **Cartera por añada (cohorte):** créditos vivos agrupados por su mes de desembolso.

## Cadencia y grano

- **Frecuencia:** SEMANAL (corte los miércoles, igual que la cuota semanal).
- **Grano:** UNA fila por **crédito vivo** a la `fecha_corte`. No se agrega: el detalle
  por crédito es lo que habilita el aging y la proyección fina.
- **Cobertura:** todos los créditos activos (vigentes y en mora) + los castigados del
  período. Los cancelados/pagados totalmente pueden omitirse (o venir con estado y saldo
  en cero).

## Campos (todos los que SISMO-V3 puede entregar)

Leyenda: **REQ** = obligatorio · OPC = opcional (mejora la precisión).

| # | Campo | Tipo | REQ | Descripción / uso |
|---|-------|------|-----|-------------------|
| 1 | `credito_id` | texto | REQ | Identificador ÚNICO del crédito en SISMO-V3. Es la llave: cada semana se actualiza (upsert) por (credito_id, fecha_corte). |
| 2 | `fecha_corte` | fecha YYYY-MM-DD | REQ | Fecha del corte semanal (el miércoles). Igual para todas las filas del archivo. |
| 3 | `cliente_id` | texto | OPC | Identificador OPACO del cliente (sin datos personales: NO nombre, NO cédula en claro). Solo para trazabilidad interna. |
| 4 | `modelo` | texto | REQ | Modelo de la moto: Raider, Apache, Sport (o el nombre exacto del catálogo). Alimenta el mix. |
| 5 | `fecha_desembolso` | fecha YYYY-MM-DD | REQ | Fecha de desembolso/originación. Define la añada (cohorte) y el inicio del cronograma. |
| 6 | `monto_financiado` | decimal COP | REQ | Monto financiado (valor del crédito a cuotas), 2 decimales. |
| 7 | `plazo_semanas` | entero | REQ | Número total de cuotas semanales del crédito. |
| 8 | `cuota_semanal` | decimal COP | REQ | Valor de cada cuota semanal. Es el recaudo esperado por semana del crédito. |
| 9 | `cuotas_pagadas` | entero | REQ | Número de cuotas efectivamente pagadas a la fecha de corte. |
| 10 | `cuotas_vencidas` | entero | REQ | Número de cuotas ya vencidas y NO pagadas a la fecha de corte. |
| 11 | `dias_mora` | entero >= 0 | REQ | Días de atraso de la cuota vencida más antigua sin pagar. 0 = al día. Determina el tramo de aging. |
| 12 | `saldo_en_mora` | decimal COP | REQ | Monto vencido y no pagado a la fecha de corte. Es el aging POR MONTO. |
| 13 | `saldo_pendiente` | decimal COP | REQ | Saldo total por cobrar del crédito (lo que falta, al día + en mora). Alimenta la cartera total. |
| 14 | `fecha_ultimo_pago` | fecha YYYY-MM-DD | OPC | Fecha del último pago registrado (vacío si nunca ha pagado). Valida/deriva `dias_mora`. |
| 15 | `estado` | texto | REQ | Estado del crédito: `vigente` \| `en_mora` \| `castigado`. En minúsculas, exacto. |

## Tramos de aging (los deriva COMPAS de `dias_mora`)

| Tramo | Rango de `dias_mora` |
|-------|----------------------|
| Al día | 0 |
| 1-30 | 1 a 30 |
| 31-60 | 31 a 60 |
| 61-90 | 61 a 90 |
| 90+ | 91 o más |

COMPAS agrupa los créditos por tramo y suma `saldo_en_mora` (aging por monto) y cuenta
créditos (aging por número). No se inventa nada: todo sale de `dias_mora` + `saldo_en_mora`.

## Reglas de formato (para que la carga no falle)

- **Codificación:** UTF-8.
- **Formato de archivo:** CSV (separador `,`) o Excel (.xlsx), una sola hoja, con
  encabezado en la primera fila usando EXACTAMENTE los nombres de campo de la tabla.
- **Fechas:** `YYYY-MM-DD` estricto (ej. `2026-07-22`). Sin hora, sin zona horaria.
- **Montos:** número con punto decimal y 2 decimales (ej. `164900.00`). SIN separador
  de miles, SIN símbolo de moneda. Todo en COP.
- **Enteros:** sin decimales (ej. `78`).
- **Vacíos:** los campos OPC pueden ir vacíos; los REQ nunca vacíos.
- **Sin datos personales** en el archivo (Ley 1581): nada de nombres ni cédulas en
  claro; usar `cliente_id` opaco.

## Idempotencia y carga

- La llave de deduplicación es **(`credito_id`, `fecha_corte`)**: recargar el mismo
  corte NO duplica (pisa). Se conserva el histórico de cortes para ver la evolución del
  aging; la vista usa el corte más reciente.
- Un crédito que desaparece del archivo se considera cancelado/pagado a esa fecha.

## Ejemplo (una fila, CSV)

```
credito_id,fecha_corte,cliente_id,modelo,fecha_desembolso,monto_financiado,plazo_semanas,cuota_semanal,cuotas_pagadas,cuotas_vencidas,dias_mora,saldo_en_mora,saldo_pendiente,fecha_ultimo_pago,estado
CR-000123,2026-07-22,CLI-4471,Raider,2026-01-14,6435000.00,78,164900.00,20,2,14,329800.00,9564200.00,2026-07-01,en_mora
```

## Entrega

- **Fase actual:** SISMO-V3 genera este archivo semanal; se **sube a COMPAS** por la
  pantalla de carga (igual que las cargas bancarias). Es lo que desarrollamos ahora.
- **Fase siguiente:** COMPAS lo lee **directo** de SISMO-V3 (mismo clúster / conexión),
  sin subida manual. El contrato de campos es el mismo; solo cambia el transporte.
