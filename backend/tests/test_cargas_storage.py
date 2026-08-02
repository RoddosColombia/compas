# backend/tests/test_cargas_storage.py
"""PR-S3 — almacenamiento del original en S3 (DISP-02 / M-04). Parte UNITARIA.

MARCADO PARA AUDITORÍA KIMI (gate PR-S3). Estos tests NO tocan Mongo: ejercen
`cargas/storage.py` con un cliente S3 stub inyectado (boto3 real solo en prod).
El cableado end-to-end (procesar_carga) vive en el archivo real-mongo hermano.
"""

import pytest
from app.cargas import storage


class _StubS3:
    """Cliente S3 mínimo: registra put_object o falla (fail-closed)."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[dict] = []
        self.fail = fail

    def put_object(self, **kw) -> dict:
        if self.fail:
            raise RuntimeError("s3 caído")
        self.calls.append(kw)
        return {"ETag": "stub"}


def test_clave_original_formato():
    assert storage.clave_original("abc123", ".xlsx") == "originales/abc123.xlsx"
    assert storage.clave_original("def", ".pdf") == "originales/def.pdf"


def test_subir_original_pone_objeto_y_devuelve_uri(tmp_path):
    p = tmp_path / "ext.xlsx"
    p.write_bytes(b"contenido-binario-del-extracto")
    client = _StubS3()
    uri = storage.subir_original(
        client=client,
        bucket="compas-archivo",
        key="originales/abc123.xlsx",
        archivo_path=str(p),
    )
    assert uri == "s3://compas-archivo/originales/abc123.xlsx"
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["Bucket"] == "compas-archivo"
    assert call["Key"] == "originales/abc123.xlsx"
    assert call["Body"] == b"contenido-binario-del-extracto"


def test_subir_original_propaga_error_del_cliente(tmp_path):
    # Fail-closed: cualquier error de boto3 se propaga (el caller no persiste nada).
    p = tmp_path / "ext.xlsx"
    p.write_bytes(b"x")
    client = _StubS3(fail=True)
    with pytest.raises(RuntimeError):
        storage.subir_original(
            client=client, bucket="b", key="originales/x.xlsx", archivo_path=str(p)
        )
