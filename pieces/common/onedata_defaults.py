"""Non-secret OneData defaults for SPICE testbed (host, output prefix).

Access tokens are never stored here — configure them via Domino workflow secrets,
``ONEDATA_TOKEN`` / ``ONEDATA_TOKEN_FILE`` env vars, or GitLab CI ``ONEDATA_ACCESS_TOKEN``.
"""

DEFAULT_ONEZONE_HOST = "data.spice-platform.eu"
DEFAULT_OUTPUT_DIR = "onedata:///FilipsSpace/run"
