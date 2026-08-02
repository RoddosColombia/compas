# backend/app/cargas/storage.py
"""Almacenamiento del original de cada extracto en S3 (DISP-02 / M-04).

El original de toda carga bancaria debe quedar re-procesable (Spec §1.6, Kimi M-04).
En producción vive en `s3://{bucket}/originales/{hash}{ext}`, en un bucket con Object
Lock COMPLIANCE (retención fijada al CREAR el bucket, nunca desde aquí). El cliente
boto3 se construye perezosamente desde `Settings` y es INYECTABLE, para que los tests
usen un stub sin credenciales ni red.

Fail-closed: `subir_original` propaga cualquier error de boto3 — `procesar_carga` corre
la subida ANTES de insertar nada, así que un fallo aborta la carga sin persistir.
"""

from functools import lru_cache


@lru_cache
def get_s3_client():
    """Cliente boto3 S3 perezoso (una sola instancia) desde Settings. boto3 se
    importa aquí dentro para no exigirlo cuando S3 no es el destino (dev con
    dir_originales) ni en los tests, que inyectan un stub."""
    import boto3

    from app.config import get_settings

    s = get_settings()
    return boto3.client(
        "s3",
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key,
    )


def clave_original(archivo_hash: str, ext: str) -> str:
    """Key del objeto S3 (sin el prefijo s3://bucket): originales/{hash}{ext}."""
    return f"originales/{archivo_hash}{ext}"


def subir_original(*, client, bucket: str, key: str, archivo_path: str) -> str:
    """Sube el original a S3 y devuelve la URI `s3://{bucket}/{key}`.

    Propaga cualquier excepción del cliente (fail-closed en el caller). `client` es
    inyectable (boto3 real en prod, stub en tests)."""
    with open(archivo_path, "rb") as f:
        client.put_object(Bucket=bucket, Key=key, Body=f.read())
    return f"s3://{bucket}/{key}"
