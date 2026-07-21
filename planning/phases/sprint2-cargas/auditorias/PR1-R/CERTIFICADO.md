# CERTIFICADO KIMI — sprint2-cargas · R-PR1

**Veredicto:** ✅ **GO CONDICIONADO — 9.2 / 10.** Fecha: 2026-07-20. **Merge de `f9985fe` autorizado.**

4/4 hallazgos cerrados: M-1 (CR-S2, catálogo 31, `transaccion.creada` en toda creación manual), M-2 ("superado lo pedido": MAX_FILAS en loop + `_validar_zip` sin extraer), B-1 (DuplicateKeyError→409), B-2 (Consulta 403 ✓).

## ⚠️ Polizón detectado (no declarado en la solicitud)
`f9985fe` también modifica la **regla 12** de CLAUDE.md: permite `docs/INVENTARIO-SECRETOS.xlsx` con secretos reales en el repo (decisión CEO; allowlist gitleaks; quedan en el historial). Contradice el baseline certificado. Lo acota: credenciales limitadas a recursos COMPAS (F-19/F-27) y repo de 2 personas. **El fallo principal es de proceso**: una decisión de gobernanza de este calibre merece su propia CR.

## Condición del GO → **CR-S3 esta semana**
(a) alcance exacto: allowlist = path exacto `docs/INVENTARIO-SECRETOS.xlsx`, no patrón de carpeta;
(b) regla dura: **rotar todo el contenido ANTES de cualquier ampliación** de exposición o membresía;
(c) evaluación seria de alternativa (AWS SSM/Secrets Manager, Doppler, o gestor existente) o mínimo cifrado fuera del repo (SOPS/age);
(d) si se queda: acceso = las mismas 2 personas de B3, revisado al añadir colaboradores.
La prueba adversarial C3 corrió ANTES de la excepción — sigue protegiendo todo lo demás.

**Nota del auditor:** "el proceso volvió a su cauce — la rama sigue sin mergear y el gate va antes del merge."
