# A14 en PRODUCCIÓN — `GET /api/v1/proyeccion` idéntico pre/post deploy

**Fecha:** 2026-07-30 · **PR:** #46 (E2 backend) mergeado a `main` (`7bc8316`).

La verificación que le importa al CEO: no que A14 pase en tests, sino que **desplegar E2
no mueva la proyección real**. Se tomó la foto del endpoint en prod ANTES de mergear y
DESPUÉS del deploy, y se comparó bit a bit.

## Método (sin datos sensibles)

- Endpoint: `GET https://api.compas.roddos.com/api/v1/proyeccion`.
- Parámetros **PINNEADOS** e idénticos en ambas fotos: `escenario=base`, `horizonte_meses=180`,
  `mes_inicio=2026-07`. Pinnear `mes_inicio` es obligatorio: su default es `today_bogota()`,
  y un cambio de día entre las dos fotos habría producido un diff **ajeno al IVA** (falso
  positivo).
- El JSON completo (proyección financiera) se comparó en local; en el repo se guarda solo el
  **sha256 + metadata** de cada foto (`foto_proyeccion_{pre,post}_deploy.sha256`).
- Confirmación de que el código NUEVO estaba vivo antes de la foto post: `openapi.json` de
  prod ya incluía `facturas/cargar` (endpoint nuevo de E2).

## Resultado

| | status | bytes | sha256 |
|---|---|---|---|
| pre-deploy | 200 | 94925 | `18fe9f13…e19d6bc9` |
| post-deploy | 200 | 94925 | `18fe9f13…e19d6bc9` |

**`diff` de los dos JSON: vacío (exit 0). sha256 idénticos.**

→ **A14 verificado en producción: `GET /proyeccion` idéntico bit a bit.** La compuerta
`IVA_ALIMENTA_PROYECCION` (sembrada apagada) sostiene D-12; la migración corrida en prod y la
colección de facturas vacía no alteran la proyección. Cero hallazgo.
