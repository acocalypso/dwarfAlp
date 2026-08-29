# Contributing to dwarfAlp

Thank you for improving dwarfAlp. Contributions can target application code,
documentation, tests, hardware observations, or sanitized protocol evidence. A
physical telescope is not required for ordinary work.

## Set up the repository

Use Python 3.10 or newer and the locked development environment:

```powershell
git clone https://github.com/acocalypso/dwarfAlp.git
cd dwarfAlp
python -m pip install uv
uv sync --extra development --locked
```

The complete environment and local launch instructions are in
[development setup](docs/development/setup.md).

## Make a focused change

- Base work on the repository's current default branch and keep each pull request
  limited to one coherent problem.
- Preserve model-specific behavior and do not generalize protocol evidence from one
  device or firmware without tests and clear qualification.
- Do not include credentials, private device data, firmware binaries, APKs, extracted
  workspaces, build output, or runtime state.
- Avoid hand-editing generated protobuf bindings or generated API-site JSON.

## Validate

Run before opening a pull request:

```powershell
uv run ruff check .
uv run pytest -p no:cacheprovider
uv run python scripts/generate_protos.py --check
uv run python scripts/check_markdown_links.py
```

Run `uv run python scripts/generate_api_site.py` when application routes, documented
HTTP/protocol inventory, or site generation changes. Review and commit only intended
generated output.

## Protocol and protobuf changes

Protocol conclusions should identify their evidence: official behavior, hardware
observation, APK/firmware analysis, inference, or unresolved hypothesis. Include the
module/command IDs, request and response or notification paths, affected models and
firmware, and an error-state test where practical.

After changing a `.proto` file, run:

```powershell
uv run python scripts/generate_protos.py
uv run python scripts/generate_protos.py --check
```

Commit source schemas and generated bindings together. See the
[protobuf guide](docs/development/protobuf.md).

## Hardware tests and observations

Hardware tests are explicitly opt-in and never run in normal CI. Only enable them
with an attended, unobstructed device after reading
[hardware-test safety](docs/development/testing.md#hardware-tests-are-opt-in).
Document any possible movement, focusing, filter actuation, exposure, or state change.

Sanitize Wi-Fi credentials, BLE credentials/addresses, IP addresses as appropriate,
device IDs, file paths, coordinates, target/image metadata, and personal information
before sharing logs or captures. Never submit `var/connectivity.json`.

## Documentation and pull requests

Use the existing audience split: end-user guidance under `docs/getting-started` or
`docs/user-guide`, contributor material under `docs/development`, and evidence-based
reverse engineering under the specialist research sections. Update links and run the
link checker after moving a document.

A pull request should explain:

- the problem and user-visible effect
- the models/firmware or platforms affected
- the implementation and important tradeoffs
- tests and manual validation actually performed
- remaining uncertainty, especially for untested hardware

All contributions are licensed under the repository's GNU GPL v3.0 license.
