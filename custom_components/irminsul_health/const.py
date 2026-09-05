"""Constants for Irminsul Health."""

from typing import Final

DOMAIN: Final = "irminsul_health"
PLATFORMS: Final = ["sensor"]

CONF_SUBJECT_ID: Final = "subject_id"
CONF_SUBJECT_NAME: Final = "subject_name"
CONF_WEBHOOK_ID: Final = "webhook_id"
CONF_ROTATE_WEBHOOK: Final = "rotate_webhook"

EVENT_OBSERVATION_RECEIVED: Final = f"{DOMAIN}_observation_received"

STORAGE_VERSION: Final = 1
MAX_OBSERVATIONS: Final = 500
MAX_REQUEST_BYTES: Final = 256 * 1024

METRIC_URIC_ACID: Final = "uric_acid"
UNIT_URIC_ACID: Final = "µmol/L"
