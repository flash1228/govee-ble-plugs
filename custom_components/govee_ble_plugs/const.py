DOMAIN = "govee_ble_plugs"
MANUFACTURER = "Govee"

# Config-entry schema version. New entries are stamped with these; entries stamped lower
# are brought forward by ``async_migrate_entry``. Bump MINOR for backwards-compatible
# changes (an older build still reads the entry), MAJOR when the data itself changes shape.
#   1.2 — power-factor sensor became a diagnostic entity, disabled by default.
CONFIG_ENTRY_VERSION = 1
CONFIG_ENTRY_MINOR_VERSION = 2

CONF_ENABLE_POLLING = "enable_polling"
DEFAULT_ENABLE_POLLING = True

# Advanced/test option: route a device that has a bespoke driver (currently only the H6163
# light) through the generic codec-driven driver instead, so the generic path can be
# validated against real hardware. Default off = bespoke behaviour unchanged.
CONF_GENERIC_DRIVER = "generic_driver"
DEFAULT_GENERIC_DRIVER = False
