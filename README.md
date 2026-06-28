# UC3.3 Industry SG VRE — Sustainable Model (Domino)

Domino piece repository for the sustainable energy workflow (OneData I/O, MRK/PV/battery simulation, investment KPIs, dashboard).

## Repository layout (production)

| Path | Purpose |
|------|---------|
| `pieces/` | Domino pieces and shared `common/` helpers |
| `pieces/catalog/` | Default PV/battery catalog JSON (bundled in images) |
| `dependencies/` | Container build (`Dockerfile`, `requirements.txt`) |
| `config.toml` | Registry, version, repository metadata |
| `.domino/` | Compiled piece metadata (updated by CI) |
| `sus_onedata.customization` | Domino import (GitHub / GHCR) |
| `sus_onedata.spice.customization` | Domino import (SPICE / Harbor) |
| `sus_onedata.json` | Workflows pack export |
| `scripts/sync_onedata_customization.py` | Regenerate customization + JSON |
| `scripts/export_workflow_json.py` | Refresh GitLab workflows pack |


## GitLab CI / Harbor

| Variable | Description |
|----------|-------------|
| `CI_PUSH_TOKEN` | Project access token with `write_repository` (+ `api`) |
| `CI_RELEASE_TOKEN` | Project access token with `api` |
| `CONTAINER_REGISTRY` | `harbor.testbed.spice-platform.eu` |
| `CONTAINER_REGISTRY_USERNAME` | Harbor user/robot (e.g. `partner`) |
| `CONTAINER_REGISTRY_PASSWORD` | Harbor password from vault |

