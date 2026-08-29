# Protobuf bindings

The `.proto` files under `src/dwarf_alpaca/proto/` are source. The adjacent
`*_pb2.py` files are generated but intentionally versioned so clean installations can
import the runtime without a compiler.

The canonical generator is cross-platform and uses the pinned `grpcio-tools`
development dependency:

```powershell
uv sync --extra development --locked
uv run python scripts/generate_protos.py
uv run python scripts/generate_protos.py --check
```

The generator rewrites imports for package-relative use. `--check` generates into a
temporary directory and fails when a checked-in binding is missing, extra, or stale.

`gen_pb2.sh` remains at the repository root as a compatibility wrapper for historical
links. It delegates to the canonical Python generator and should not gain a separate
generation workflow.

When changing a schema, commit the `.proto`, regenerated bindings, tests, and evidence
for protocol conclusions together. Do not hand-edit `*_pb2.py`.
