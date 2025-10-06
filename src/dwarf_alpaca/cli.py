from __future__ import annotations

import asyncio
import logging
import time
from logging.handlers import RotatingFileHandler
from typing import Optional

from .config.settings import Settings, load_settings
from .server import run_server
from .provisioning.cli import provision_command, provision_guide_command
from .provisioning.workflow import create_state_store
from .dwarf.session import configure_session, get_session

logger = logging.getLogger(__name__)

_START_LOG_HANDLER_FLAG = "_dwarf_alpaca_start_handler"


def _configure_start_logging(settings: Settings) -> None:
    """Ensure `dwarf-alpaca start` logs are persisted to a rotating file."""

    try:
        log_dir = settings.state_directory / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "dwarf-alpaca-start.log"
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("cli.start.logfile_init_failed", error=str(exc))
        return

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if getattr(handler, _START_LOG_HANDLER_FLAG, False):
            return

    handler = RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    setattr(handler, _START_LOG_HANDLER_FLAG, True)
    root_logger.addHandler(handler)
    logger.info("cli.start.logfile_enabled path=%s", log_path)


async def _preflight_session(
    settings: Settings,
    *,
    timeout: float = 120.0,
    interval: float = 5.0,
) -> None:
    """Ensure the DWARF is reachable and master lock is acquired before serving."""

    configure_session(settings)
    session = await get_session()
    deadline = time.monotonic() + max(timeout, 0.0)
    attempt = 1

    while True:
        try:
            await session.acquire("telescope")
        except Exception as exc:  # pragma: no cover - hardware dependent
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.error(
                    "cli.start.connection_failed ip=%s attempt=%s error=%s",
                    settings.dwarf_ap_ip,
                    attempt,
                    exc,
                )
                raise
            logger.warning(
                "cli.start.connection_retry ip=%s attempt=%s error=%s",
                settings.dwarf_ap_ip,
                attempt,
                exc,
            )
            await asyncio.sleep(max(interval, 0.5))
            attempt += 1
            continue

        try:
            has_master_lock = getattr(session, "has_master_lock", False)
            logger.info(
                "cli.start.connected ip=%s attempt=%s master_lock=%s",
                settings.dwarf_ap_ip,
                attempt,
                has_master_lock,
            )
        finally:
            await session.release("telescope")
        return


async def start_command(
    *,
    settings: Settings,
    ssid: Optional[str],
    password: Optional[str],
    adapter: Optional[str],
    ble_password: Optional[str],
    device_address: Optional[str],
    skip_provision: bool,
    timeout: float,
    interval: float,
    ws_client_id: Optional[str],
) -> None:
    """Provision the DWARF (optionally) and launch the Alpaca server."""

    _configure_start_logging(settings)

    if ws_client_id:
        settings.dwarf_ws_client_id = ws_client_id

    if not skip_provision:
        if ssid:
            if not password:
                raise SystemExit("Wi-Fi password is required when specifying an SSID.")
            await provision_command(
                settings=settings,
                ssid=ssid,
                password=password,
                adapter=adapter,
                ble_password=ble_password,
                device_address=device_address,
            )
        else:
            logger.info("cli.start.running_guide")
            await provision_guide_command(
                settings=settings,
                adapter=adapter,
                ble_password=ble_password,
            )

    state_store = create_state_store(settings.state_directory)
    state = state_store.load()
    if state.sta_ip:
        settings.dwarf_ap_ip = state.sta_ip
        logger.info("cli.start.using_sta_ip ip=%s mode=%s", state.sta_ip, state.mode)
    else:
        logger.info(
            "cli.start.using_config_ip ip=%s mode=%s",
            settings.dwarf_ap_ip,
            state.mode,
        )

    if not settings.force_simulation:
        await _preflight_session(
            settings,
            timeout=timeout,
            interval=interval,
        )
    else:
        logger.info("cli.start.simulation_mode_enabled")

    await run_server(settings)


def main() -> None:
    """CLI entry point for running the Alpaca server or performing provisioning tasks."""
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="DWARF 3 Alpaca Server")
    subparsers = parser.add_subparsers(dest="command")

    server_parser = subparsers.add_parser("serve", help="Run the Alpaca server")
    server_parser.add_argument(
        "--config",
        type=str,
        help="Path to a settings YAML file to load in addition to environment variables.",
    )
    server_parser.add_argument(
        "--ws-client-id",
        type=str,
        help="Override the websocket client identifier used to talk to the DWARF.",
    )

    start_parser = subparsers.add_parser(
        "start",
        help="Provision (optional), verify, and run the Alpaca server.",
    )
    start_parser.add_argument(
        "--config",
        type=str,
        help="Path to a settings YAML file to load in addition to environment variables.",
    )
    start_parser.add_argument(
        "--ssid",
        type=str,
        help="Provision target Wi-Fi SSID (omit to run the interactive guide or reuse saved configuration).",
    )
    start_parser.add_argument(
        "--password",
        type=str,
        help="Provision target Wi-Fi password (required if --ssid is provided).",
    )
    start_parser.add_argument(
        "--adapter",
        type=str,
        help="Optional BLE adapter identifier (platform-specific).",
    )
    start_parser.add_argument(
        "--ble-password",
        type=str,
        help="Override the BLE password (defaults to DWARF_12345678 or settings value).",
    )
    start_parser.add_argument(
        "--device-address",
        type=str,
        help="Specify the BLE device address to skip auto-discovery.",
    )
    start_parser.add_argument(
        "--skip-provision",
        action="store_true",
        help="Start the server without running BLE provisioning.",
    )
    start_parser.add_argument(
        "--wait-timeout",
        type=float,
        default=180.0,
        help="Seconds to wait for DWARF connectivity before failing (default: 180).",
    )
    start_parser.add_argument(
        "--wait-interval",
        type=float,
        default=5.0,
        help="Seconds between connectivity checks during startup (default: 5).",
    )
    start_parser.add_argument(
        "--ws-client-id",
        type=str,
        help="Override the websocket client identifier used to talk to the DWARF.",
    )

    provision_parser = subparsers.add_parser(
        "provision",
        help="Provision DWARF 3 onto a local Wi-Fi network via BLE.",
    )
    provision_parser.add_argument("ssid", type=str, help="Target Wi-Fi SSID")
    provision_parser.add_argument("password", type=str, help="Wi-Fi password")
    provision_parser.add_argument(
        "--adapter",
        type=str,
        help="Optional BLE adapter identifier (platform-specific).",
    )
    provision_parser.add_argument(
        "--ble-password",
        type=str,
        help="Override the BLE password (defaults to DWARF_12345678 or settings value).",
    )

    guide_parser = subparsers.add_parser(
        "guide",
        help="Interactive BLE guide to discover DWARF devices and provision Wi-Fi.",
    )
    guide_parser.add_argument(
        "--adapter",
        type=str,
        help="Optional BLE adapter identifier (platform-specific).",
    )
    guide_parser.add_argument(
        "--ble-password",
        type=str,
        help="Pre-seed the BLE password to skip the interactive prompt.",
    )

    args = parser.parse_args()

    if args.command == "guide":
        settings = load_settings(config_path=None)
        asyncio.run(
            provision_guide_command(
                settings=settings,
                adapter=args.adapter,
                ble_password=args.ble_password,
            )
        )
        return

    if args.command == "start":
        settings = load_settings(config_path=args.config)
        asyncio.run(
            start_command(
                settings=settings,
                ssid=args.ssid,
                password=args.password,
                adapter=args.adapter,
                ble_password=args.ble_password,
                device_address=args.device_address,
                skip_provision=args.skip_provision,
                timeout=args.wait_timeout,
                interval=args.wait_interval,
                ws_client_id=args.ws_client_id,
            )
        )
        return

    if args.command == "provision":
        settings = load_settings(config_path=None)
        asyncio.run(
            provision_command(
                settings=settings,
                ssid=args.ssid,
                password=args.password,
                adapter=args.adapter,
                ble_password=args.ble_password,
            )
        )
        return

    # default to server mode
    config_path: Optional[str] = getattr(args, "config", None)
    settings = load_settings(config_path=config_path)
    if getattr(args, "ws_client_id", None):
        settings.dwarf_ws_client_id = args.ws_client_id
    asyncio.run(run_server(settings))
