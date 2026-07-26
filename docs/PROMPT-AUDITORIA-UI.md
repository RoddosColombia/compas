# Prompt de auditoría de UI — COMPAS (pegar en Claude para Chrome)

> Copia todo lo de abajo de la línea `---` y pégalo en Claude para Chrome con la
> pestaña abierta en `https://compas.roddos.com`. Claude navegará y validará vista por
> vista. Las capturas de errores guárdalas en `revision-ui/` para que Claude Code las
> revise.

---

Eres un auditor de QA. Estás validando **COMPAS**, el sistema de presupuesto y flujo de
caja de RODDOS, desplegado en **https://compas.roddos.com** (API en
`https://api.compas.roddos.com`). Tu trabajo es verificar que **lo que existe hoy
funciona**, sin romper nada (solo navegar y leer; no cargues ni borres datos).

## Contexto de datos (lo que YA está cargado — mar–jul 2026, cuenta Global66)
- **1.270 movimientos** curados. Meses con data: **marzo a julio 2026**.
- **Caja acumulada final ≈ $704.700.000**. Flujo por mes: mar +1,2M · abr +20,7M ·
  may −14,6M · jun +807M (mes de un aporte de capital grande) · jul −110M.
- **Ingresos:** Recaudo operativo ≈ **$390M** (185 movs) + **Aportes de capital**
  ≈ **$1.040M** (8 movs, rubro separado, NO es recaudo operativo).
- **Egresos** ≈ **$725M** repartidos en 5 grupos (Costo de producto ~245M, Nómina
  ~206M, Deudas ~112M, Otros ~95M, Operación ~68M).
- **Resultado operativo ≈ −$335M** (la operación quema caja; el superávit lo sostiene
  el capital de inversionistas).
- Rubros alineados al Plan de Cuentas (código de 3 niveles: 0110, 2070, 5060, …).

## Pasos
1. **Login**: inicia sesión con la cuenta del CEO (te la da el usuario; completa MFA
   si lo pide). Verifica que entra y redirige a **/inicio**.
2. **Selector de mes**: confirma que puedes elegir meses **2026-03 a 2026-07** y que
   traen datos (los meses fuera de ese rango pueden salir vacíos — es normal).
3. **Recorre las 8 vistas del menú** (grupos: Principal / Planeación y control /
   Operación) y para CADA una verifica: (a) carga sin pantalla en blanco ni error,
   (b) no hay errores en la consola del navegador (F12 → Console), (c) los montos se
   ven en formato peso colombiano ($1.234.567), (d) nada dice "NaN", "undefined",
   "Infinity" ni fechas raras.

   | Vista | Ruta | Qué esperar |
   |---|---|---|
   | **Inicio** | /inicio | KPIs de caja; "Realidad vs proyección"; caja del mes seleccionado |
   | **Proyecciones** | /proyeccion | Serie proyectada de caja hacia el futuro (meses adelante) |
   | **Escenarios** | /escenarios | Comparación de escenarios (base/optimista/…) |
   | **Presupuesto** | /control | Control de egresos por rubro del mes; ejecutado vs presupuesto |
   | **IVA** | /iva | Liquidación de IVA. **Estado vacío esperado** (aún no hay facturas cargadas) — NO es error |
   | **Dashboards** | /dashboards | Cobranza, colocación, cartera por añada, y "Mora por tramo". **La mora saldrá vacía** (aún no hay LoanTape de SISMO) — NO es error |
   | **Reportes** | /reportes | Reportes disponibles |
   | **Datos** | /datos | Captura/cargas (caja inicial, supuestos) |

4. **Chequeo de coherencia de cifras** (donde la vista las muestre):
   - ¿La caja/ingreso operativo se ve cerca de **$390M** y NO de $1.430M? (si aparece
     $1.430M como "recaudo", el capital se está mezclando → repórtalo).
   - ¿Los egresos por grupo suman ~$725M?
   - ¿Aparecen los 5 grupos de egreso y el ingreso operativo por separado?
5. **Responsivo y accesos**: reduce la ventana a móvil; confirma que el menú y las
   vistas no se rompen. Verifica que el ítem **Datos** existe (requiere permiso de
   gestión).

## Estados vacíos que NO son bugs (no los reportes como error)
- **IVA** sin facturas.
- **Mora por tramo / aging** sin LoanTape.
- Meses fuera de mar–jul 2026 sin datos.

## Cómo reportar
Por cada problema real: (1) toma **captura de pantalla**, (2) guárdala en la carpeta
`revision-ui/` con nombre descriptivo (`error-<vista>-<detalle>.png`), (3) anota la
URL, qué esperabas y qué viste. Al final, entrega una **tabla resumen**:

| Vista | ¿Carga? | ¿Errores consola? | Cifras coherentes | Captura | Nota |
|---|---|---|---|---|---|

Sé literal y objetivo: reporta solo lo que ves. Si algo funciona bien, dilo también.
