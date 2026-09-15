# Estado · Chat de Andres (Planner 1)

**Ultima actualizacion:** 2026-09-14 (plan de migracion de cluster cerrado).

## Tarea en curso

Ninguna abierta. Ultima tarea planificada: **migracion de COMPAS al cluster propio `compas-prod`** (Atlas M0, `us-east-1`, cuenta `info@roddos.com`).

## Resumen del plan (3 lineas)

1. Dos fases en paralelo: Sergio prepara `compas-prod` (proyecto, tier/region, allowlist, rol y usuarios, URIs en INVENTARIO); Jorge congela escrituras, reconfirma el nodo sano y saca el dump con la escalera del CRITICO 1, guardando copia permanente en disco del CEO.
2. Fase secuencial de un solo owner (Jorge): restore con `--drop`, verificacion de 28 colecciones y conteos identicos e indices, prueba manual de que `audit_writer` rechaza update/delete, switch de las DOS env vars en Render en un solo guardado con respaldo `_OLD`, smoke del CEO, 1 hora de observacion, borrado de las `_OLD` al no-retorno.
3. Cierre documental (Sergio): correccion fechada en RUNBOOK §2, tracker, commit de cierre. Cuatro gates del CEO (G1 borrar/crear cluster, G2 dump degradado, G3 switch, G4 no-retorno) y tres niveles de rollback (RB-1 sin perdida, RB-2 pierde sesiones del smoke, RB-3 pierde escrituras de negocio).

## Entregable

`docs/equipo/entregas/PLAN-migracion-cluster.md` · 4 fases, 23 pasos (A1-A6, B1-B6, C1-C9, D1-D4), 8 precondiciones, 4 gates, tabla de rollback.

Reparto: Sergio 10 pasos (Fase A + Fase D), Jorge 15 pasos (Fase B + Fase C). A y B paralelas; C y D secuenciales. Sergio queda sin trabajo entre A6 y C9, dicho explicito.

## Avisos escalados al CEO (seccion 0 del plan)

- Ninguna decision cerrada del handshake descansa sobre un hecho falso.
- Aviso 1: usuarios y rol de Atlas son por PROYECTO; si `compas-prod` comparte proyecto con `sismo-v3`, ya existen y no se recrean (paso A4 ramifica).
- Aviso 2: el test de CI de inmutabilidad NO vigila produccion; la verificacion del enforcement es manual (paso C3).
- Aviso 3: `compas_app` con `readWrite` si puede tocar `audit_log` a nivel de BD; se replica tal cual, endurecer requiere CR.
- Aviso 4: tres hechos sin verificar por Jose (URI directa a nodo, ids de winget, plazo de auto-pausa M0). No bloquean.

## Pendiente inmediato

Nada mio. Siguiente rol: Jorge y Sergio (builders) con el plan. Si el CEO quiere cerrar los hechos del Aviso 4 antes de la ventana, van a Jose (seccion 9 del plan).

## Como retomar

Pegar el boilerplate de arranque de `docs/equipo/roles/andres-planner.md`. Leer este estado. Si hay feedback del CEO o de Claude (arquitecto) sobre el plan, aplicarlo sobre `docs/equipo/entregas/PLAN-migracion-cluster.md` sin reabrir decisiones del handshake.

## Historial reciente

- 2026-09-14 · PLAN-migracion-cluster.md escrito y commiteado en `main`.
