from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
)

from .const import DOMAIN
from .coordinator import GoveePlugDataUpdateCoordinator
from .entity import GoveePlugEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up govee plug based on a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: GoveePlugDataUpdateCoordinator = entry_data["coordinator"]
    entities = []
    if coordinator.api:
        port_names = coordinator.api.port_names()
    else:
        # Device not discovered yet — only create switch(es) if the configured model is a
        # switch-type device (plug/appliance), so lights/sensors don't get phantom switches.
        from .devices import find_definition_by_model
        from .devices.capabilities import SwitchCaps

        defn = find_definition_by_model(entry_data.get("model") or "")
        if defn is None or defn.category not in ("plug", "appliance"):
            port_names = []
        elif isinstance(defn.caps, SwitchCaps) and defn.caps.ports:
            port_names = list(defn.caps.ports)
        else:
            port_names = [(None, None)]

    for port, port_name in port_names:
        entities.append(GoveePlugSwitch(coordinator, entry, port, port_name))
    async_add_entities(entities)


class GoveePlugSwitch(GoveePlugEntity, SwitchEntity):
    """Govee switch class."""

    _attr_device_class = SwitchDeviceClass.OUTLET
    _attr_translation_key = "power"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        if not self.coordinator.api:
            return
        await self.coordinator.api.async_turn_on(self._port)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        if not self.coordinator.api:
            return
        await self.coordinator.api.async_turn_off(self._port)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        if not self.coordinator.api:
            return None
        return self.coordinator.api.is_on(self._port)

    @property
    def available(self) -> bool:
        """Available once discovered. Plugs gate on parsed state; optimistic devices
        (appliances, whose state isn't reliably carried by broadcasts) are available as
        soon as the API exists."""
        api = self.coordinator.api
        if api is None:
            return False
        if getattr(api, "optimistic_switch", False):
            return True
        return api.is_on(self._port) is not None
