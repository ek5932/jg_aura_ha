import asyncio
import hashlib
import urllib
from datetime import datetime
import logging
import xml.etree.ElementTree as ET
import aiohttp
from . import thermostat
from . import hotwater
from . import httpClient
from . import gateway

_LOGGER = logging.getLogger(__name__)

APPID = "1097"
RUN_MODES = [
    "Auto", 
    "High",
    "Medium",
    "Low",
    "Party",
    "Away",
    "Frost"
    ]
RUN_MODES_WITH_DURATION = [
    "Party",
    "Away"
    ]

# There are more modes than actual presets. However, if a mode does not match a preset
# HA can show the mode, but the preset is left blank. As such, make sure the values match
# the 'preset' you want to display.
MODES = [
	"OFFLINE",
	"Auto", # Auto High
	"Auto", # Auto Medium
	"Auto", # Auto Low
	"High",
	"Medium",
	"Low",
	"Party",
	"Away",
	"Frost",
	"ON",
	"ON",
	"UNDEFINED",
	"UNDEFINED",
	"UNDEFINED",
	"UNDEFINED",
	"OFFLINE",
	"Auto", # Auto High
	"Auto", # Auto Medium
	"Auto", # Auto Low
	"High",
	"Medium",
	"Low",
	"Party",
	"Frost",
	"ON",
]

class JGClient:
    gatewayDeviceId = None
    loggedIn = False
    securityToken = None
    hashedPassword = None

    def __init__(self, host, email, password):
        self.host = host
        self.email = email
        self.hashedPassword = hashlib.md5(password.encode()).hexdigest()

    async def __login(self):
        _LOGGER.info(f'Attempting login for "{self.email}"')
        self.gatewayDeviceId = await self.__requestGatewayDeviceId()
        _LOGGER.info(f'Connected to device "{self.gatewayDeviceId}"')
        self.loggedIn = True

    async def GetThermostats(self):
        if not self.loggedIn:
            await self.__login()
        return await self.__requestDevices(self.__extractThermostats)

    async def GetHotWater(self):
        if not self.loggedIn:
            await self.__login()
        return await self.__requestDevices(self.__extractHotWater)

    async def SetThermostatPreset(self, deviceId, stateName):
        if not self.loggedIn:
            await self.__login()
        return await self.__setPreset(deviceId, stateName)

    async def SetThermostatTemperature(self, deviceId, temperature):
        if not self.loggedIn:
            await self.__login()
        return await self.__setTemperature(deviceId, temperature)

    async def SetHotWater(self, deviceId, is_on):
        if not self.loggedIn:
            await self.__login()
        return await self.__setHotWater(deviceId, is_on)

    async def __requestGatewayDeviceId(self):
        loginUrl = f'{self.host}/userLogin?appId={APPID}&name={self.email}&password={self.hashedPassword}&timestamp={self.__getDate()}'
        result = await httpClient.callUrlWithRetry(loginUrl)
        userId = self.__extractUserDetailsFromLogin(result)

        deviceIdUrl = f'{self.host}/getDeviceList?secToken={self.securityToken}&userId={userId}&timestamp={self.__getDate()}'
        result = await httpClient.callUrlWithRetry(deviceIdUrl)
        return self.__extractGatewayDeviceId(result)

    async def __requestDevices(self, parseFunction):
        url = f'{self.host}/setMultiDeviceAttributes2?secToken={self.securityToken}&devId={self.gatewayDeviceId}&name1=B01&value1=5&timestamp={self.__getDate()}'  
        await self.__fetchUrlWithLoginRetry(url)
        
        url = f'{self.host}/getDeviceAttributesWithValues?secToken={self.securityToken}&devId={self.gatewayDeviceId}&deviceTypeId=1&timestamp={self.__getDate()}'  
        responseContent = await self.__fetchUrlWithLoginRetry(url)
        return parseFunction(responseContent)

    async def __setPreset(self, deviceId, stateName):
        # Currently duration cannot be passed, hard code it to 1. It is a 2-char padded string
        duration = str(1).zfill(2) if stateName in RUN_MODES_WITH_DURATION else ""

        payload = urllib.parse.quote(f'!{deviceId}{chr(int(RUN_MODES.index(stateName) + 35))}{duration}')
        url = f'{self.host}/setMultiDeviceAttributes2?secToken={self.securityToken}&devId={self.gatewayDeviceId}&name1=B05&value1={payload}&timestamp={self.__getDate()}'
        result = await self.__fetchUrlWithLoginRetry(url)
        self.__validateOperationResponse(result)

    async def __setTemperature(self, deviceId, temperature):
        payload = urllib.parse.quote(f'!{deviceId}{chr(int(temperature * 2 + 32))}')
        url = f'{self.host}/setMultiDeviceAttributes2?secToken={self.securityToken}&devId={self.gatewayDeviceId}&name1=B06&value1={payload}&timestamp={self.__getDate()}'
        result = await self.__fetchUrlWithLoginRetry(url)
        self.__validateOperationResponse(result)

    async def __setHotWater(self, deviceId, is_on):
        heating_state = '# ' if is_on else f'$ '
        payload = urllib.parse.quote(f'!{deviceId}{heating_state}')
        url = f'{self.host}/setMultiDeviceAttributes2?secToken={self.securityToken}&devId={self.gatewayDeviceId}&name1=B05&value1={payload}&timestamp={self.__getDate()}'
        result = await self.__fetchUrlWithLoginRetry(url)
        self.__validateOperationResponse(result)

    async def __fetchUrlWithLoginRetry(self, url):
        responseContent = None
        for attempt in range(3):
            async with aiohttp.ClientSession() as session:
                async with session.get(f'{url}') as response:
                    if response.status == 200:
                        responseContent = await response.text()
                        break

                    _LOGGER.error(f'login to URL {url} was not successful; retrying (Status code {response.status}).')
                    self.loggedIn = False
                    await self.__login()

        if responseContent == None:
            raise Exception('Unexpected error making request.') 
        return responseContent

    def __extractGatewayDeviceId(self, response):
        tree = ET.fromstring(response)
        devId = tree.findtext('devList/devId')
        return devId

    def __extractUserDetailsFromLogin(self, response):
        tree = ET.fromstring(response)
        self.securityToken = tree.findtext('securityToken')
        userId = tree.findtext('userId')
        return userId

    def __getDate(self):
        return str(datetime.now().timestamp()).replace('.', '')

    def __extractThermostats(self, response):
        tree = ET.fromstring(response)
        try:
            # The names of the thermostats are stored under the 'Name' nodes.
            thermostatDisplayNodeNames = ['S02', 'S03']

            # A device supports up to 30 thermostats, with up to 3 nodes containing
            # their summaries (10 each). They are identified by keyed names
            summaryNodeNames = ['001', '002', '003']

            items = []
            for element in tree.findall("./attrList"):
                name = element.findtext("name")
                if name in thermostatDisplayNodeNames or name in summaryNodeNames:
                    items.append({
                        'Id':element.findtext("id"),
                        'Name': name,
                        'Value':element.findtext("value")
                                        .replace('&lt;','<')
                                        .replace('&gt;','>')
                                        .replace('&amp;', '&')
                    })

            summaries = {}
            for entryValue in (x.get('Value') for x in items if x.get('Name') in summaryNodeNames):
                for element in (entryValue[i:i+8] for i in range(0, len(entryValue), 8)):
                    if len(element) == 8:
                        id = element[0:4]
                        summaries[id] = element[4:]
        
            thermostats = []
            for entryValue in (x.get('Value') for x in items if x.get('Name') in thermostatDisplayNodeNames):
                for element in (x for x in entryValue.split(',') if len(x) > 4):
                    id = element[0:4]
                    summary = summaries[id]
                    thermostats.append(
                        thermostat.Thermostat(
                            id, 
                            element[4:], 
                            ord(summary[1]) - 32 > 9, 
                            MODES[ord(summary[1]) - 32],
                            (ord(summary[2]) - 32) * 0.5, 
                            (ord(summary[3]) - 32) * 0.5))
            
            return gateway.Gateway('JG-Gateway', 'JG-Gateway', thermostats)

        except Exception as e:
            _LOGGER.error(f'Unexpected error processing results: {e}\n {response}')
            raise

    def __extractHotWater(self, response):
        tree = ET.fromstring(response)
        try:
            items = []
            for element in tree.findall("./attrList"):
                items.append(
                    {
                        'Id':element.findtext("id"), 
                        'Value':element.findtext("value")
                                        .replace('&lt;','<')
                                        .replace('&gt;','>')
                                        .replace('&amp;', '&')
                    })

            hotWaterOn = False
            hotWaterId = list(filter(lambda item: item.get('Id') == '2272', items))[0].get('Value').strip()
            hotWaterId = hotWaterId[1:len(hotWaterId)-1]

            ## '2569Q3 0' - on
            ## '2569Q$ 0' - off
            ## '2569Q! 0' - auto
            summaryValue = list(filter(lambda item: item.get('Id') == '2257', items))[0].get('Value')
            for element in [summaryValue[i:i+8] for i in range(0, len(summaryValue), 8)]:
                if hotWaterId in element:
                    hotWaterOn = element[0:len(hotWaterId) + 2].endswith('3')
                    break

            return hotwater.HotWater(hotWaterId, hotWaterOn)

        except Exception as e:
            _LOGGER.error(f'Unexpected error processing results: {e}\n {response}')
            raise

    def __validateOperationResponse(self, response):
        tree = ET.fromstring(response)
        responseCode = tree.find('retCode')
        if responseCode.text != '0':
            raise Exception('Operation failed; unexpected response code.\n{response}')
