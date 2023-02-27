from __future__ import annotations

import logging

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_HOST
from . import CONF_REFRESH_RATE
from . import jg_client
from . import thermostat
from datetime import timedelta

from homeassistant.const import (
	TEMP_CELSIUS, 
	ATTR_TEMPERATURE
)
from homeassistant.components.climate.const import (
	CURRENT_HVAC_HEAT,
	CURRENT_HVAC_IDLE,
	HVAC_MODE_HEAT,
	HVAC_MODE_OFF,
	SUPPORT_TARGET_TEMPERATURE,
	SUPPORT_PRESET_MODE,
	PRESET_AWAY 
)
from homeassistant.components.climate import ClimateEntity
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

	thermostatEntities = []
	client = jg_client.JGClient(host, email, password)

	async def async_update_data():
		return await client.GetThermostats()

	def find_thermostat_data(id):
		for t in coordinator.data.thermostats:
			if t.id == id:
				return t
		return None

	def update_entities():
		for entity in thermostatEntities:
			data = find_thermostat_data(entity.id)
			entity.setValues(data)
			entity.async_write_ha_state()

	coordinator = DataUpdateCoordinator(
		hass,
		_LOGGER,
		name = "climate",
		update_method = async_update_data,
		update_interval = timedelta(seconds = discovery_info[CONF_REFRESH_RATE])
	)

	coordinator.async_add_listener(update_entities)
	
	await coordinator.async_config_entry_first_refresh()

	for thermostat in coordinator.data.thermostats:
		jgt = JGAuraThermostat(coordinator, client, coordinator.data.id, thermostat.id, thermostat.name, thermostat.on)
		jgt.setValues(thermostat)
		thermostatEntities.append(jgt)

	async_add_entities(thermostatEntities)


class JGAuraThermostat(CoordinatorEntity, ClimateEntity):
	def __init__(self, coordinator, client, gateway_id, id, name, is_on):
		super().__init__(coordinator)

		self._gateway_id = gateway_id
		self._id = id
		self._client = client

		self._attr_unique_id = "jg_aura-" + str(id)
		self._attr_icon = "mdi:temperature-celsius"

		self._name = name

		if is_on == True:
			self._hvac_mode = HVAC_MODE_HEAT
		else:
			self._hvac_mode = HVAC_MODE_OFF
		
		self._hvac_list = [HVAC_MODE_OFF, HVAC_MODE_HEAT]
		self._support_flags = SUPPORT_TARGET_TEMPERATURE | SUPPORT_PRESET_MODE
		self._preset_mode = "Low"

	@property
	def id(self):
		return self._id

	@property
	def name(self):
		return self._name

	@property
	def max_temp(self):
		return 35

	@property
	def min_temp(self):
		return 5

	@property
	def temperature_unit(self):
		return TEMP_CELSIUS

	@property
	def current_temperature(self):
		return self._current_temp

	@property
	def target_temperature(self):
		return self._target_temp

	@property
	def hvac_mode(self):
		return self._hvac_mode
	
	@property
	def hvac_action(self):
		return self._hvac_mode

	@property
	def hvac_modes(self):
		return self._hvac_list

	@property
	def preset_mode(self):
		return self._preset_mode

	@property
	def preset_modes(self):
		return jg_client.RUN_MODES
	
	@property
	def supported_features(self):
		return self._support_flags

	async def async_set_temperature(self, **kwargs):
		temperature = kwargs.get(ATTR_TEMPERATURE)
		if temperature is None:
			return

		self._target_temp = temperature
		await self._client.SetThermostatTemperature(self._id, temperature)

	async def async_set_preset_mode(self, preset_mode):
		self._preset_mode = preset_mode
		await self._client.SetThermostatPreset(self._id, preset_mode)

	def setValues(self, thermostat: thermostat.Thermostat):
		self._current_temp = thermostat.tempCurrent
		self._target_temp = thermostat.tempSetPoint
		self._preset_mode = thermostat.stateName
		if thermostat.on == True:
			self._hvac_mode = HVAC_MODE_HEAT
		else:
			self._hvac_mode = HVAC_MODE_OFF