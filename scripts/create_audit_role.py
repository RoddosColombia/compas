#!/usr/bin/env python
"""Crea (idempotente) el rol `audit_writer` y el usuario `compas_audit` en Mongo.

DoD #6 / RUNBOOK §2: el usuario general de la app NO tiene update/remove sobre
`audit_log`; solo `compas_audit` (rol `audit_writer` = insert+find) escribe. Ambos
sobre la MISMA database `compas` (no una db separada — así el audit_log entra en el
dump/restore/archivado).

La contraseña NUNCA va por argv (visible en ps/historial/CI, CWE-798/214): se lee de
COMPAS_AUDIT_PWD o por getpass, sin default, mínimo 16 chars. Actualiza rol Y contraseña.

Uso (contra un mongod con auth de admin, usuario con privilegio userAdmin sobre la db):
    COMPAS_AUDIT_PWD=... python scripts/create_audit_role.py "<MONGODB_ADMIN_URI>" [db=compas]

Idempotente: si el rol/usuario ya existen, actualiza privilegios y contraseña sin fallar.
Lo corre el operador (RUNBOOK §2) y el CI de la Sesión 3 sobre un mongod efímero con auth
para validar los tests @requires_real_mongo. NO se ejecuta en runtime de la app.

NOTA de tier Atlas (Kimi H-01): createRole/createUser están disponibles en M10+ (el cluster
de este proyecto). En clusters Free/Flex están BLOQUEADOS → usar Atlas UI o Admin API (los
cambios de custom roles tardan ~30 s). Ver RUNBOOK §2.
"""

from __future__ import annotations

import getpass
import os
import sys

from pymongo import MongoClient
from pymongo.errors import OperationFailure

# Textos/códigos con los que Atlas Free/Flex rechaza los comandos no soportados.
_UNSUPPORTED = ("not allowed", "unsupported", "not supported", "command not found")


def _fail_if_unsupported(e: OperationFailure) -> None:
    msg = str(e).lower()
    if any(s in msg for s in _UNSUPPORTED):
        sys.exit(
            "Atlas rechazó el comando (¿cluster Free/Flex?). En esos tiers "
            "createRole/createUser están bloqueados: crea el rol audit_writer y el "
            "usuario compas_audit por Atlas UI / Admin API. Ver RUNBOOK §2."
        )


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('Uso: COMPAS_AUDIT_PWD=... python scripts/create_audit_role.py "<MONGODB_ADMIN_URI>" [db]')
    uri = sys.argv[1]
    db_name = sys.argv[2] if len(sys.argv) > 2 else "compas"

    audit_pwd = os.environ.get("COMPAS_AUDIT_PWD") or getpass.getpass(
        "Password para compas_audit (>=16 chars): "
    )
    if len(audit_pwd) < 16:
        sys.exit("La contraseña de compas_audit debe tener al menos 16 caracteres.")

    client: MongoClient = MongoClient(uri)
    db = client[db_name]

    # 1) Rol audit_writer: insert + find sobre audit_log; SIN update/remove.
    role = {
        "createRole": "audit_writer",
        "privileges": [
            {
                "resource": {"db": db_name, "collection": "audit_log"},
                "actions": ["insert", "find"],
            }
        ],
        "roles": [],
    }
    try:
        db.command(role)
        print("Rol audit_writer creado.")
    except OperationFailure as e:
        _fail_if_unsupported(e)  # H-01: tier Free/Flex
        if e.code == 51002 or "already exists" in str(e).lower():  # Role already exists
            db.command({
                "updateRole": "audit_writer",
                "privileges": role["privileges"],
                "roles": [],
            })
            print("Rol audit_writer ya existía → privilegios actualizados.")
        else:
            raise

    # 2) Usuario compas_audit con ese rol.
    user = {
        "createUser": "compas_audit",
        "pwd": audit_pwd,
        "roles": [{"role": "audit_writer", "db": db_name}],
    }
    try:
        db.command(user)
        print("Usuario compas_audit creado.")
    except OperationFailure as e:
        _fail_if_unsupported(e)  # H-01: tier Free/Flex
        if e.code == 51003 or "already exists" in str(e).lower():  # User already exists
            # H-02: actualizar roles Y contraseña (coherente con la rotación
            # semestral del RUNBOOK §8; sin pwd, la URI rotada dejaría de autenticar).
            db.command({
                "updateUser": "compas_audit",
                "pwd": audit_pwd,
                "roles": [{"role": "audit_writer", "db": db_name}],
            })
            print("Usuario compas_audit ya existía → roles y contraseña actualizados.")
        else:
            raise

    # 3) Índice forense (Kimi O3): lo crea el setup con privilegios de admin, NO el
    # rol audit_writer (solo insert+find). Idempotente (createIndex no duplica).
    # Debe coincidir con AUDIT_INDEXES de app/audit/models.py.
    db["audit_log"].create_index(
        [("entidad", 1), ("entidad_id", 1), ("timestamp", 1)],
        name="forense_entidad_ts",
    )
    print("Índice forense (entidad, entidad_id, timestamp) asegurado.")

    print(
        "Listo. El usuario general de la app NO debe tener update/remove sobre "
        f"{db_name}.audit_log (verificar su rol readWrite acotado)."
    )


if __name__ == "__main__":
    main()
