DOMAIN = "govee_ble_plugs"
MANUFACTURER = "Govee"

CONF_ENABLE_POLLING = "enable_polling"
DEFAULT_ENABLE_POLLING = True

# Advanced/test option: route a device that has a bespoke driver (currently only the H6163
# light) through the generic codec-driven driver instead, so the generic path can be
# validated against real hardware. Default off = bespoke behaviour unchanged.
CONF_GENERIC_DRIVER = "generic_driver"
DEFAULT_GENERIC_DRIVER = False
