# MCP and tooling evaluation

| Tool/server | Purpose and value | Security implications | Recommendation |
|---|---|---|---|
| Context7 | Current official/project docs; used for Ghidra headless options | sends documentation queries, not firmware | Keep; useful supporting tool |
| Local WSL shell/filesystem | `file`, `readelf`, strings, archive and module inspection | broad local file access; commands must remain static/read-only | Primary tool; sufficient for this phase |
| Ghidra headless | ARM disassembly/decompilation, xrefs, call graphs | parses untrusted binaries in Java and creates analysis projects; isolated in a restricted container | Added as a pinned, reproducible Docker workflow |
| PyGhidra-MCP (`clearbluejar/pyghidra-mcp`) | MCP access to Ghidra functions, decompiler and xrefs | exposes Ghidra project/filesystem through a server; same parser risk plus service surface | Potentially useful, but not necessary or installed |
| radare2/Rizin MCP | interactive binary analysis equivalent | parser/service risk and environment change | No callable server found; CLI/Ghidra would suffice |
| SQLite MCP | database schema/data exploration | may expose private device data | Not needed; no database in bundle, and read-only CLI is preferable |
| GitHub/source lookup | upstream matching and source research | external queries reveal search terms; license/provenance must be checked | Available in principle; no uncertain component required it |
| Binwalk | recursive signature/container scanning | third-party parsers; false positives | Context7 did not resolve a trustworthy package; formats were cross-checked without it |

The checked-in environment uses Ghidra 12.1.3 headlessly with post-analysis
export, a per-file timeout, and disposable projects. Runtime networking is
disabled, artifacts are mounted read-only, and imported binaries are never run.
See [`tools/reverse-engineering/README.md`](../../tools/reverse-engineering/README.md).
