from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_HOST
from . import jg_client

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:

    host = discovery_info[CONF_HOST]
    email = discovery_info[CONF_EMAIL]
    password = discovery_info[CONF_PASSWORD]
    
    client = jg_client.JGClient(host, email, password)
    hotWater = await client.GetHotWater()
    switch = HotWaterSwitch(client, hotWater.id, hotWater.is_on)
    
    async def async_update_data():
        return await client.GetHotWater()

    def update_entities():
        switch.setState(coordinator.data.is_on)

    coordinator = DataUpdateCoordinator(
		hass,
		_LOGGER,
		name = "switch",
		update_method = async_update_data,
		update_interval = timedelta(seconds = 5)
	)

    coordinator.async_add_listener(update_entities)
    await coordinator.async_config_entry_first_refresh()
    async_add_entities([switch], True)

class HotWaterSwitch(SwitchEntity):
    def __init__(self, client, id, is_on):
        self._id = id
        self._is_on = is_on
        self._client = client
        self._attr_unique_id = "jg_aura-hotwater-" + str(id)

    @property
    def is_on(self):
        return self._is_on

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return "Hot Water"

    def setState(self, is_on):
        self._is_on = is_on

    async def async_turn_on(self):
        await self._client.SetHotWater(self._id, True)
        self._is_on = True

    async def async_turn_off(self):
        await self._client.SetHotWater(self._id, False)
        self._is_on = False
