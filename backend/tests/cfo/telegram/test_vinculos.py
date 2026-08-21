# backend/tests/cfo/telegram/test_vinculos.py
"""FABS · lógica de la allowlist Telegram: alta/baja (con auditoría CR-CFO-2) y
resolución telegram_id -> user_id. `vincular`/`desvincular` son operaciones de
estado (admin) — la auditoría NO es fail-soft: si emit_audit falla, propaga."""

import pytest
from app.cfo.telegram import vinculos


@pytest.mark.asyncio
async def test_vincular_audita(monkeypatch):
    creados = []

    async def fake_crear(v):
        creados.append(v)

    eventos = []

    async def fake_emit(evento, entidad, entidad_id=None, actor_id=None, metadata=None):
        eventos.append((str(evento), metadata))

    monkeypatch.setattr(
        "app.cfo.telegram.vinculos.repositorio.crear_vinculo", fake_crear
    )
    monkeypatch.setattr("app.cfo.telegram.vinculos.emit_audit", fake_emit)
    await vinculos.vincular(111, "u1", admin_id="admin")
    assert creados[0].telegram_id == 111 and creados[0].user_id == "u1"
    assert eventos[0][0] == "cfo.vinculo_creado"


@pytest.mark.asyncio
async def test_vincular_audita_con_metadata_y_actor(monkeypatch):
    async def fake_crear(v):
        pass

    eventos = []

    async def fake_emit(evento, entidad, entidad_id=None, actor_id=None, metadata=None):
        eventos.append(
            {
                "evento": str(evento),
                "entidad": entidad,
                "actor_id": actor_id,
                "metadata": metadata,
            }
        )

    monkeypatch.setattr(
        "app.cfo.telegram.vinculos.repositorio.crear_vinculo", fake_crear
    )
    monkeypatch.setattr("app.cfo.telegram.vinculos.emit_audit", fake_emit)
    await vinculos.vincular(222, "u2", admin_id="admin-1")
    e = eventos[0]
    assert e["actor_id"] == "admin-1"
    assert e["metadata"] == {"telegram_id": 222, "user_id": "u2"}


@pytest.mark.asyncio
async def test_vincular_propaga_si_ya_existe(monkeypatch):
    """El vínculo es uno-a-uno (B-3): crear_vinculo levanta si telegram_id o
    user_id ya están tomados. vincular() NO debe tragarse ese error (y, como no
    llega a crearse, tampoco debe auditar)."""

    async def fake_crear(v):
        raise RuntimeError("duplicado")

    eventos = []

    async def fake_emit(evento, entidad, entidad_id=None, actor_id=None, metadata=None):
        eventos.append(evento)

    monkeypatch.setattr(
        "app.cfo.telegram.vinculos.repositorio.crear_vinculo", fake_crear
    )
    monkeypatch.setattr("app.cfo.telegram.vinculos.emit_audit", fake_emit)
    with pytest.raises(RuntimeError):
        await vinculos.vincular(333, "u3", admin_id="admin")
    assert eventos == []


@pytest.mark.asyncio
async def test_vincular_propaga_si_audit_falla(monkeypatch):
    """La auditoría de vincular NO es fail-soft: es una operación de estado admin,
    no una lectura (a diferencia del Q&A, que envuelve emit_audit en fail-soft en
    el servicio). Si emit_audit falla, vincular() NO debe tragarse el error."""

    async def fake_crear(v):
        pass

    async def fake_emit_que_falla(
        evento, entidad, entidad_id=None, actor_id=None, metadata=None
    ):
        raise RuntimeError("audit no configurado")

    monkeypatch.setattr(
        "app.cfo.telegram.vinculos.repositorio.crear_vinculo", fake_crear
    )
    monkeypatch.setattr("app.cfo.telegram.vinculos.emit_audit", fake_emit_que_falla)

    with pytest.raises(RuntimeError):
        await vinculos.vincular(444, "u4", admin_id="admin")


@pytest.mark.asyncio
async def test_desvincular_elimina_y_audita(monkeypatch):
    async def fake_eliminar(telegram_id):
        assert telegram_id == 111
        return True

    eventos = []

    async def fake_emit(evento, entidad, entidad_id=None, actor_id=None, metadata=None):
        eventos.append((str(evento), metadata, actor_id))

    monkeypatch.setattr(
        "app.cfo.telegram.vinculos.repositorio.eliminar_vinculo", fake_eliminar
    )
    monkeypatch.setattr("app.cfo.telegram.vinculos.emit_audit", fake_emit)

    ok = await vinculos.desvincular(111, admin_id="admin")

    assert ok is True
    assert eventos[0][0] == "cfo.vinculo_eliminado"
    assert eventos[0][1] == {"telegram_id": 111}
    assert eventos[0][2] == "admin"


@pytest.mark.asyncio
async def test_desvincular_sin_vinculo_no_audita(monkeypatch):
    async def fake_eliminar(telegram_id):
        return False

    eventos = []

    async def fake_emit(evento, entidad, entidad_id=None, actor_id=None, metadata=None):
        eventos.append(evento)

    monkeypatch.setattr(
        "app.cfo.telegram.vinculos.repositorio.eliminar_vinculo", fake_eliminar
    )
    monkeypatch.setattr("app.cfo.telegram.vinculos.emit_audit", fake_emit)

    ok = await vinculos.desvincular(999, admin_id="admin")

    assert ok is False
    assert eventos == []  # nada que auditar: no había vínculo que eliminar


@pytest.mark.asyncio
async def test_resolver_delega_al_repositorio(monkeypatch):
    async def fake_resolver(telegram_id):
        return "u1" if telegram_id == 111 else None

    monkeypatch.setattr(
        "app.cfo.telegram.vinculos.repositorio.resolver_usuario", fake_resolver
    )

    assert await vinculos.resolver(111) == "u1"
    assert await vinculos.resolver(999) is None
