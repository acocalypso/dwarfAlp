import asyncio
import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf.session import DwarfSession


@pytest.mark.asyncio
async def test_acquire_rolls_back_on_failure(monkeypatch):
    settings = Settings(force_simulation=False)
    session = DwarfSession(settings)

    async def failing_ensure_ws():
        raise RuntimeError("ws failure")

    monkeypatch.setattr(session, "_ensure_ws", failing_ensure_ws)

    with pytest.raises(RuntimeError):
        await session.acquire("camera")

    assert session._refs["camera"] == 0


@pytest.mark.asyncio
async def test_has_master_lock_property_reflects_state():
    settings = Settings(force_simulation=True)
    session = DwarfSession(settings)

    assert session.has_master_lock is False
    session._master_lock_acquired = True
    assert session.has_master_lock is True
