"""Keys used by the control state stream."""

PRESS_DEWATER = "press/dewater"
PRESS_STATE = "press/state"
PRESS_GAIN = "press/gain"

DRY_PROCEDURE = "dry/procedure"
DRY_SPEED = "dry/speed"
DRY_CURVE = "dry/curve"

STEAM_DRAIN = "steam/drain"
STEAM_VALVE = "steam/valve"
STEAM_BASELINE = "steam/baseline"

GLUE_ROLL = "glue/roll"
GLUE_PUMP = "glue/pump"
GLUE_ALARM = "glue/alarm"
GLUE_CONC = "glue/concentration"

CAL_NIP = "cal/nip"
CAL_SPEED = "cal/speed"

REEL_PROCEDURE = "reel/procedure"
REEL_SPOOL = "reel/spool"
REEL_RETRACT = "reel/retract"

BROKE_PROCEDURE = "broke/procedure"
BROKE_LATCH = "broke/latch"

WATER_MAP = "water/map"
WATER_PROFILE = "water/profile"
WATER_SAMPLES = "water/samples"

VERSION_PREFIX = "version/"
CONFIRMATION_PREFIX = "confirmation/"
ARTIFACT_PREFIX = "artifact/"
BATCH_PREFIX = "batch/"


def version_key(name: str) -> str:
    return VERSION_PREFIX + name


def confirmation_key(confirmation_id: str) -> str:
    return CONFIRMATION_PREFIX + confirmation_id


def artifact_key(kind: str, name: str) -> str:
    return f"{ARTIFACT_PREFIX}{kind}/{name}"


def batch_key(batch_id: str) -> str:
    return BATCH_PREFIX + batch_id
