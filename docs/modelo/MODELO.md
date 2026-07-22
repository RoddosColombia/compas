# MODELO — el Excel que COMPAS reemplaza (base de construcción)

> Destilado de `Flujo de pagos deudas.xlsx` (fuente viva en OneDrive:
> `BP 26/Tecnologia/Compas/`). Aquí va la **estructura y la lógica**, NO los datos
> reales (montos/nombres = PII, Ley 1581). Este doc es el **contrato funcional**:
> cada capacidad de COMPAS debe reproducir lo que hace la hoja correspondiente.
> Código de referencia: `docs/modelo/referencia/Dashboard_Artefacto.jsx`.
> Fijado: 2026-07-22.

## Las 10 hojas → capacidades de COMPAS

| Hoja | Qué hace | Capacidad | Estado |
|---|---|---|---|
| **Inicio** | Portada: mes de control (`=TEXT(Control!A4,"mmmm yyyy")`) | — | — |
| **Control** | CONTROL DE EGRESOS por mes: `Mes · Presupuesto · Ejecutado · Disponible · % Ejecutado · Caja disponible` | Vista Control | ✅ |
| **Presupuesto** (143×93) | Motor de presupuesto + seguimiento; meses rodantes (`=EOMONTH(TODAY(),-2)+1`); azul=presupuesto | Motor sugerido + acotar/aprobar | ✅ |
| **Base real egresos** | Movimientos de egreso reales: `Fecha · Descripción · Categoría · Valor · Mes · ID banco` | **C1 categorías + C3 auto-clasificación** | ❌ |
| **Base real ingresos** | Movimientos de ingreso reales: `Fecha · Descripción · Valor · Mes · ID banco` | C3 (ingresos → Recaudo) | ❌ |
| **Proyeccion ingresos** (47 cols) | Proyección de venta de motos → ingreso (jul-26→dic-2030) | **C7 recaudo/ventas (M10)** | ❌ |
| **Flujo pago deudas** | Cronograma de pago a acreedores: `Empresa · Valor total · Cuota · [mes×N]` | **Fecha de pago a proveedores (M6)** | ❌ |
| **Facturas Auteco** | Compras de moto: `Fecha · Factura · Und Raider/Sport/Apache · Subtotal · Seguro · IVA 19%` | **IVA + costo de producto (M7)** | ❌ |
| **Pagos semana** | Pagos de la próxima semana vs `Caja disponible hoy (=Control!H54)` | Planeación semanal de caja | ❌ |
| **Segundo semestre** | Flujo de caja jul–dic (proyección) | **C7 proyección de caja** | ❌ |

## Taxonomía REAL de categorías (semilla para C1/C3 — 31 categorías)

Esto reemplaza/afina la semilla genérica actual. Son categorías de negocio (no PII).
Agrupar en los 5 grupos del dominio al sembrarlas:

- **Costo de producto:** Producto · SOAT/Matrículas · Seguros (Hunter)
- **Operación:** Transporte/peajes/combustible/parqueo · Cafetería · Mercado y aseo ·
  Tecnología y software · Gastos de representación · Papelería · Marketing y publicidad ·
  Servicios públicos y telecom · Mobiliario/planta/equipo · Viajes corporativos ·
  Grúas y traslados · Dotación empleados · Freelance
- **Nómina:** Sueldos directivos · Sueldos empleados · Bonificaciones · Beneficios Heads · Planillas anteriores
- **Deudas y obligaciones:** Préstamos · Deudas proveedores anteriores · Deudas tarjetas de crédito
- **Otros:** Impuestos · Otros gastos · Gastos bancarios · Gastos financieros ·
  Asuntos legales · Gastos notariales · Arriendos
- **Sistema (no editables):** Por clasificar · Recaudo · Ajuste de conciliación

## C3 — Auto-clasificación (cómo funciona en el Excel, a replicar)

En `Base real egresos` cada movimiento tiene ya su `Categoría` asignada. La clasificación
se hace por **patrón de la descripción del movimiento** (ver el mapeo que ya construimos
descripción→categoría del Global66). Regla de COMPAS:
- Al cargar, cada movimiento se compara contra reglas administrables (contiene texto X →
  categoría Y). La primera que aplique gana; si ninguna aplica → **'Por clasificar'**.
- Clasificar manualmente un movimiento en 'Por clasificar' puede **crear/afinar una regla**.
- Ingresos (Abono / Recibido de…) → **Recaudo** (rubro de sistema INGRESO).

## C7 — Proyección de ingresos (drivers del Excel)

Hoja `Proyeccion ingresos`, por mes (jul-26 → dic-2030). Drivers:
`Motos mes · Plazo de pago · Precio venta · Costo moto · Cuota semanal · Cuota inicial`
+ fila `REAL VS PROYECTADO`. El **recaudo se discrimina** en **cuota inicial** (entrada) vs
**cuota semanal de crédito** (recaudo del crédito) — requisito CEO. De aquí salen:
proyección de caja, objetivos de venta para sostenibilidad, y el pre-llenado del % de
crecimiento del presupuesto.

## Modelos adicionales en la carpeta (referencias, no en repo)

- `MODELO SIMULADOR 2030 …xlsm` (~10MB, macros) — simulador de ventas/crecimiento a 2030
  (Raider/Sport/Apache). Molde de la capa predictiva de ventas/sostenibilidad; se destila
  aparte cuando ataquemos C7.
- `Plantilla Bancolombia enero 2026.xlsx` / `Plantilla BBVA enero 2026.xlsx` — formatos xlsx
  reales que esperan los parsers (fixtures S1-01).
- Extractos Global66 `abr/may/jun 2026` (PDF) — datos de la migración abr–jul.

## Regla de oro

Cuando construya cualquier capacidad, la pregunta es: **¿reproduce lo que hace su hoja
en este Excel?** Si no, me desvié. Y siempre hacia la **predicción/decisión** (norte),
no hacia el registro contable.
