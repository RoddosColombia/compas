# Gate G1 — lo que TÚ haces (en simple) y lo que hago YO

> El `G1-CHECKLIST.md` y el `PLAYBOOK-BLOQUE-C.md` son para el detalle técnico. **Este archivo es
> el resumen humano.** Solo quedan 4 cosas tuyas; el resto lo hago yo o ya está hecho.

## ✅ Ya está hecho (no tienes que tocar nada)
- **Todo el código de seguridad** (auth, MFA, cabeceras, CI). Auditado por Kimi, todo GO.
- **A5/A6**: la CI corre verde en GitHub (los 5 jobs). **Cerrado.**
- **Budget de GitHub**: NO tocar nada. El CI cabe en los minutos gratis.

## 🙋 Lo que hago YO por ti (solo necesito que me pases unos datos)
| Tarea | Qué necesito de ti |
|---|---|
| **C1** — verificar que staging responde "listo" | la **URL de staging** (ej. `https://compas-api-stg.onrender.com`) |
| **C4** — verificar las cabeceras de seguridad | las **URLs** de la web y la API |
| **C3** — probar que un secreto falso es bloqueado | tu **OK** para abrir un PR de prueba (secreto falso, lo borro después) |
| **A5/A6** — confirmar CI verde | ya hecho ✓ |

## 👤 Lo que solo puedes hacer TÚ (son 4, con esto cierra el Sprint 0)

### 1. Meter 2 secretos en Render  *(5 minutos, en la web de Render)*
En cada servicio (`compas-api`, `compas-jobs`, `compas-api-stg`) → pestaña **Environment** → añade:
- **`MFA_ENC_KEY`** — genera el valor **una vez** con este comando en tu terminal y pégalo:
  ```
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- **`MONGODB_URI_AUDIT`** — la cadena del usuario `compas_audit` (la armas en el paso 2).
> Consejo: cuando crees la contraseña del paso 2, hazla **solo letras y números** (sin `@ : / # ? &`)
> para que la cadena de conexión no se rompa.

### 2. Preparar Atlas  *(copiar y pegar 8 comandos en tu terminal)*
Necesitas tu **cadena de admin de Atlas** (la que tiene usuario/clave de administrador).
Corre esto **primero con `compas_stg`** y cuando salga OK, repite cambiando `compas_stg` por `compas`:
```bash
# reemplaza <ADMIN_URI> y <URI_STG> por tus cadenas reales
COMPAS_AUDIT_PWD='claveSoloLetrasYNumeros16' python scripts/create_audit_role.py "<ADMIN_URI>" compas_stg
python scripts/create_auth_indexes.py "<URI_STG>" compas_stg
python migrations/20260901_seed_rubros.py "<URI_STG>" compas_stg
python migrations/20260901_seed_configuracion.py "<URI_STG>" compas_stg
```
Guarda lo que imprime cada comando (es la evidencia). Córrelos **dos veces** para ver "N nuevos" y luego "0 nuevos".

### 3. Probar el bloqueo de producción  *(cuando quieras)*
- En Render, confirma que `compas-api` (prod) tiene **Auto-Deploy: OFF**.
- Yo te preparo el comando del tag; al empujarlo, el deploy debe **quedar esperando tu aprobación** (no desplegar).

### 4. Anotar la región de AWS y probar la réplica  *(en la consola de AWS)*
- Anota la región de tus buckets; sube un archivo de prueba y confirma que se replica.

---

## Cómo empezamos (lo más fácil primero)
Pásame **las URLs de staging** (web y API) y **yo hago C1 y C4 ahora mismo** y te reporto el resultado.
Mientras, tú puedes ir con el paso 1 (los 2 secretos) que es el más rápido.
