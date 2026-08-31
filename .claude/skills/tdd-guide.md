---
name: tdd-guide
description: Protocolo TDD obligatorio para todo código que toque Alegra, MongoDB, la caja de RODDOS, o el motor de proyección. Escribe el test primero. Reserva esta skill para código de producción; no la aplica a docs o config.
---

# tdd-guide · AND-3 · COMPAS 2.0

**Qué es:** el orden estricto en el que Claude escribe código de producción.
Test primero, código después. La regla del CEO: si toca Alegra o MongoDB, tiene
test — no hay excepciones para «scripts rápidos».

## Cuándo se dispara (obligatorio)

- Cualquier función NUEVA en `backend/app/` que:
  - Llama a Alegra (aunque hoy es cero, la regla queda para cuando vuelva).
  - Lee o escribe en MongoDB (cualquier colección).
  - Procesa webhooks.
  - Toca reglas de dinero (Decimal, umbrales, cálculos).
- Cualquier función NUEVA en el motor o su capa post-motor (`app/proyeccion/`).
- Cualquier endpoint FastAPI nuevo (siempre exige RBAC + test de la ruta).

**No aplica** a: docs, config, migraciones idempotentes probadas manualmente
con dry-run, o refactors sin cambio semántico (rename, split de módulo).

## Protocolo (4 pasos, en orden)

1. **Escribe el test que define el comportamiento esperado.** No el código.
   El test es el diseño de la interfaz — si la interfaz sale rara, el test
   lo revela antes de que el código exista.

2. **Verifica que el test falla (RED).** Si pasa antes de que exista la
   implementación, el test no está probando lo que crees. Vuelve al paso 1.

3. **Escribe el código mínimo que lo hace pasar (GREEN).** Sin decoraciones
   sin pedir, sin abstracciones prematuras. El código elegante viene en la
   siguiente iteración, no ahora.

4. **Refactoriza si hace falta** — solo dentro del GREEN, con el test como red
   de seguridad.

## Reglas específicas de COMPAS

- **Motor intocable** (F0-2): si el test necesita que el motor cambie, la
  respuesta correcta es un test de LA CAPA POST-MOTOR (`impactos`, `service.
  py`), no del motor. Cambiar el motor exige gate `motor-parity-reviewed`.
- **Golden-master 176 meses**: cualquier PR que toque proyección corre el
  test `test_golden_master.py` — G-GM lo enforcea en CI.
- **Real-mongo tests**: usa `@pytest.mark.requires_real_mongo` cuando el test
  necesite índices únicos, transacciones multi-doc, o cambio de replica set.
  Estos tests corren en el job `backend-real-mongo` de CI.
- **Dinero es Decimal**: nunca `float(monto)`. G-SEMGREP lo enforcea.

## Composición

- Va DESPUÉS de spec-miner (`.claude/skills/spec-miner.md`): sin mapa no
  sabes qué probar.
- El `EVIDENCIA.md` de una auditoría Kimi CITA los tests de este protocolo
  como prueba de completitud — sin tests, no hay evidencia.
