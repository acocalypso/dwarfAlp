import asyncio
import json

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.provisioning.workflow import create_state_store
from dwarf_alpaca.dwarf.http_client import DwarfHttpClient


async def main() -> None:
    settings = Settings()
    state_store = create_state_store(settings.state_directory)
    state = state_store.load()
    if getattr(state, "sta_ip", None):
        settings.dwarf_ap_ip = state.sta_ip

    client = DwarfHttpClient(
        settings.dwarf_ap_ip,
        api_port=settings.dwarf_http_port,
        jpeg_port=settings.dwarf_jpeg_port,
        timeout=settings.http_timeout_seconds,
        retries=settings.http_retries,
    )
    try:
        data = await client.get_default_params_config()
    finally:
        await client.aclose()
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
