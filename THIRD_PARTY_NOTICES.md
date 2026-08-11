# Third-Party Notices

PureGamma AI integrates the following third-party components. Licenses are
reproduced by reference; do not copy third-party source into this repository.

| Component | Version | License | Notes |
|---|---|---|---|
| nautilus_trader | 1.230.0 | LGPL-3.0 | Event-driven trading engine (Rust core, pyo3 bindings). Hosted-SaaS usage is generally compatible with LGPL; **Enterprise private deployments / image distribution require legal review** of the source-availability and re-link obligations (see docs/trading/NAUTILUS_TRADER_INTEGRATION_TASK.md §5.11). The engine runs in its own container; no nautilus source is vendored here. |
| (extend this table as new components are added) | | | |

See also `apps/api/requirements.txt` and `services/nautilus-runtime/requirements.txt`
for the full dependency set and their licenses (installed via PyPI).
