# Calendario DIAN 2026 — RODDOS S.A.S.

Semilla de la clave `CALENDARIO_DIAN` de `Configuracion` (Spec §1.10). Fuente de
verdad de los vencimientos de IVA. **IVA CUATRIMESTRAL** (nunca bimestral).

- **NIT:** 901012622-1
- **Último dígito para calendario DIAN:** 2

## Vencimientos IVA cuatrimestral 2026 (declaración y pago)

| Cuatrimestre | Período      | Vencimiento (dígito 2) |
| ------------ | ------------ | ---------------------- |
| 1            | Ene–Abr 2026 | **2026-05-13**         |
| 2            | May–Ago 2026 | **2026-09-10**         |
| 3            | Sep–Dic 2026 | **2027-01-14**         |

## Representación en `Configuracion`

```json
{
  "clave": "CALENDARIO_DIAN",
  "valor_json": {
    "2026": {
      "ene_abr": "2026-05-13",
      "may_ago": "2026-09-10",
      "sep_dic": "2027-01-14"
    }
  },
  "vigente_desde": "2026-01-01"
}
```

> Editable por Admin (evento `config.actualizada`). Al publicarse el calendario
> DIAN de años siguientes, se agrega una fila nueva con la vigencia correspondiente
> (no se edita el histórico).
