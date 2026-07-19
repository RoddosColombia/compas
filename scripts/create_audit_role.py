#!/usr/bin/env python
"""Crea (idempotente) el rol `audit_writer` y el usuario `compas_audit` en Mongo.

DoD #6 / RUNBOOK §2: el usuario general de la app NO tiene update/remove sobre
`audit_log`; solo `compas_audit` (rol `audit_writer` = insert+find) escribe. Ambos
sobre la MISMA database `compas` (no una db separada — así el audit_log entra en el
dump/restore/archivado).

Uso (contra un mongod con auth de admin):
    python scripts/create_audit_role.py "<MONGODB_ADMIN_URI>" [db=compas] [pass=<compas_audit_pwd>]

Idempotente: si el rol/usuario ya existen, actualiza privilegios sin fallar. Este
script lo corre el operador (RUNBOOK) y el CI de la Sesión 3 sobre un mongod efímero
con auth para validar los tests @requires_real_mongo. NO se ejecuta en runtime de la app.
"""

from __future__ import annotations

import sys

from pymongo import MongoClient
from pymongo.errors import OperationFailure


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('Uso: python scripts/create_audit_role.py "<MONGODB_ADMIN_URI>" [db] [pass]')
    uri = sys.argv[1]
    db_name = sys.argv[2] if len(sys.argv) > 2 else "compas"
    audit_pwd = sys.argv[3] if len(sys.argv) > 3 else "CHANGE_ME"

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
        if e.code == 51003 or "already exists" in str(e).lower():  # User already exists
            db.command({
                "updateUser": "compas_audit",
                "roles": [{"role": "audit_writer", "db": db_name}],
            })
            print("Usuario compas_audit ya existía → roles actualizados.")
        else:
            raise

    print(
        "Listo. El usuario general de la app NO debe tener update/remove sobre "
        f"{db_name}.audit_log (verificar su rol readWrite acotado)."
    )


if __name__ == "__main__":
    main()
