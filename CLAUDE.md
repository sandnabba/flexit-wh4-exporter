# CLAUDE.md

Prometheus exporter and Grafana dashboard for the Flexit EcoNordic WH4 (Siemens Climatix POS3.67,
BACnet/IP). Public repo written for other WH4 owners: keep everything in English and never commit
anyone's IP addresses, hostnames or unit serial numbers.

Read [docs/development.md](docs/development.md) before changing code: it covers the architecture,
the bacpypes3 gotchas and the dashboard generator rules.

- **Only read from the unit.** BACnet has no authentication, so a write goes straight into the heat
  pump's configuration. Never write unless the user explicitly asks.
- Run scripts with `python -I`.
- Never hand-edit `grafana/wh4-dashboard.json`; change `grafana/build_dashboard.py` and regenerate.
- No tests or linters. Verify exporter changes with `--once` against a unit (`wh4_point_errors`
  must be 0) and dashboard changes in `dev/` with a headless screenshot.
- `pkill -f <pattern>` from a Bash tool call also matches the calling shell. Kill by PID.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -I wh4_exporter.py --target <unit-ip> --once
python3 -I grafana/build_dashboard.py grafana/wh4-dashboard.json
cd dev && docker compose up -d     # http://127.0.0.1:13000/d/flexit-wh4
```
