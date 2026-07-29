# CR-E2-COMPUERTA — Compuerta IVA → Proyección

**Sprint:** E2 (captura de facturas + módulo de IVA)
**Fecha:** 2026-07-28 · **Solicita/aprueba:** Andrés San Juan (CEO) · **Ejecuta:** Claude Code
**Estado:** aprobado por el CEO (instrucción definitiva 2026-07-28), pendiente de merge (PASO 4).

> **Nota de gobierno (M-3):** el *registro único de CR* (Parte VI §17 de la spec) aún no existe.
> Este CR se identifica por contenido (`CR-E2-COMPUERTA`), siguiendo la convención `CR-<sprint>`
> de `CR-D1`/`CR-D2`. **No abre una tercera serie numérica.** Debe reconciliarse en el registro
> único cuando se cree.

## Motivo

Durante la verificación previa de E2 (PASO 2) se encontró que **`GET /api/v1/proyeccion` ya consume
la colección de facturas**: `proyeccion/service.py::_iva_plan` liquida las facturas activas y resta
el IVA neto en el mes DIAN (puente C11↔C7 / PR-2b). Con la colección hoy vacía el IVA proyectado es
**cero en todos los meses, sin respaldo paramétrico** (verificado en el código).

Esto choca con la decisión **D-12** del CEO: *"No debería alimentar la proyección de caja aún;
primero hagamos que calcule el IVA y después vemos cómo lo integramos al flujo."* Sin una compuerta,
cargar la primera factura en E2 movería la caja proyectada — justo lo que D-12 prohíbe.

## Cambio autorizado

Es la **única** desviación permitida al criterio **A14** ("`GET /proyeccion` idéntico bit a bit" /
"ningún cambio en `proyeccion/`"): se autoriza modificar **solo** `_iva_plan` en
`backend/app/proyeccion/service.py`.

1. Nueva clave de `Configuracion`: **`IVA_ALIMENTA_PROYECCION`**, tipo json `{"activa": <bool>}`,
   **sembrada en `false`** (migración `20260728_e2_facturas_iva`).
2. `_iva_plan` consulta la compuerta al inicio (`_compuerta_iva_activa()`); **apagada → devuelve
   `({}, [])`** aunque haya facturas cargadas → la proyección no ve el IVA (idéntica al estado
   previo). **Encendida → comportamiento actual** (liquida y resta en el mes DIAN).
3. `motor.py`: **cero diffs**. La compuerta vive en la capa post-motor.

## Por qué no rompe A14

Con la compuerta apagada (default) y cualquier número de facturas cargadas, `_iva_plan` devuelve
`({}, [])`, exactamente como con la colección vacía. `GET /proyeccion` queda **idéntico bit a bit**.
El único camino de `Factura` a la proyección es `_iva_plan`; la reconciliación D2 usa otra colección
(`FacturaObligacion`), así que las facturas de IVA no la tocan.

## Candados (tests)

- `test_a14_compuerta_apagada_proyeccion_identica_bit_a_bit`: baseline sin facturas == proyección con
  dos facturas cargadas y compuerta apagada (igualdad de la respuesta completa).
- `test_proyeccion_iva_segun_compuerta` (parametrizado, reemplaza a `test_proyeccion_resta_iva...`):
  compuerta ON → resta el IVA en el mes DIAN y arma el fondo; OFF → IVA cero y fondo vacío.

## Auditoría

Sin evento nuevo. El evento `config.actualizada` ya existe en el catálogo (`audit/events.py`);
sembrar la clave por migración no emite. **No requiere CR de eventos (R3 satisfecha).**

## Encendido (futuro, decisión del CEO)

Cuando el CEO decida integrar el IVA al flujo, se actualiza la clave a `{"activa": true}` (dato, sin
redeploy) y `GET /proyeccion` empezará a restar el IVA en el mes DIAN. Es una decisión posterior con
el matiz de causación ya documentado (el IVA generado se causa con la factura, mientras el ingreso
por cuotas entra durante meses).

## Reversa

Quitar la clave `IVA_ALIMENTA_PROYECCION` → `_compuerta_iva_activa()` lee el default `false` →
comportamiento seguro. Revertir el commit restaura `_iva_plan` original.
