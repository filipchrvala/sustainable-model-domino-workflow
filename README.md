# UC3.3 Industry SG VRE — Sustainable Model (Domino)

Domino piece repository for the sustainable energy workflow (OneData I/O, MRK/PV/battery simulation, investment KPIs, dashboard).

## Repository layout (production)

| Path | Purpose |
|------|---------|
| `pieces/` | Domino pieces and shared `common/` helpers |
| `catalog/` | Default PV/battery catalog JSON (bundled in images) |
| `dependencies/` | Container build (`Dockerfile`, `requirements.txt`) |
| `config.toml` | Registry, version, repository metadata |
| `.domino/` | Compiled piece metadata (updated by CI) |
| `test_sus_onedata.customization` | Workflow to import in Domino |
| `requirements_0.txt` | Python deps reference for Domino organize |

## Domino deployment

1. Connect this GitLab repo as a **Pieces Repository** in Domino.
2. Wait for CI on `main` (after `config.toml` change) to build Harbor images.
3. Import `test_sus_onedata.customization` and set workflow **Secrets**:
   - `onedata_onezone_host` — e.g. `data.spice-platform.eu`
   - `onedata_token` — your OneData access token (not stored in git)
   - `onedata_output_dir` — e.g. `onedata:///YourSpace/run`
4. Seed static inputs on OneData under `inputs/` (load, prices, scenario, etc.) before the first run.

## GitLab CI / Harbor

Pipeline builds and publishes piece images to Harbor on push to `main` when `config.toml` changes.

Set these CI/CD variables (Settings → CI/CD → Variables). Mark secrets as **Masked**:

| Variable | Description |
|----------|-------------|
| `CI_PUSH_TOKEN` | Project access token with `write_repository` (+ `api`) |
| `CI_RELEASE_TOKEN` | Project access token with `api` |
| `CONTAINER_REGISTRY` | `harbor.testbed.spice-platform.eu` |
| `CONTAINER_REGISTRY_USERNAME` | Harbor user/robot (e.g. `partner`) |
| `CONTAINER_REGISTRY_PASSWORD` | Harbor password from vault |

`config.toml` `REGISTRY_NAME` must use namespace `harbor.testbed.spice-platform.eu/partner/uc3`.
