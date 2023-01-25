import hashlib
import urllib
from datetime import datetime
import logging
import xml.etree.ElementTree as ET
import aiohttp
from . import thermostat
from . import httpClient
from . import gateway

_LOGGER = logging.getLogger(__name__)

APPID = "1097"
RUN_MODES = [
    "AUTO", 
    "HIGH", 
    "MEDIUM", 
    "LOW", 
    "PARTY",
    "AWAY", 
    "FROST",
    ]
MODES = [
	"OFFLINE",
	"AUTO_HIGH",
	"AUTO_MEDIUM",
	"AUTO_LOW",
	"HIGH",
	"MEDIUM",
	"LOW",
	"PARTY",
	"AWAY",
	"FROST",
	"ON",
	"ON",
	"UNDEFINED",
	"UNDEFINED",
	"UNDEFINED",
	"OFFLINE",
	"AUTO_HIGH",
	"AUTO_MEDIUM",
	"AUTO_LOW",
	"HIGH",
	"MEDIUM",
	"LOW",
	"PARTY",
	"AWAY",
	"FROST",
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

    async def GetDevices(self):
        if not self.loggedIn:
            await self.__login()
        return await self.__requestDevices()

    async def SetPreset(self, deviceId, stateName):
        if not self.loggedIn:
            await self.__login()
        return await self.__setPreset(deviceId, stateName)

    async def SetTemprature(self, deviceId, temperature):
        if not self.loggedIn:
            await self.__login()
        return await self.__setTemprature(deviceId, temperature)

    async def __requestGatewayDeviceId(self):
        loginUrl = f'{self.host}/userLogin?appId={APPID}&name={self.email}&password={self.hashedPassword}&timestamp={self.__getDate()}'
        result = await httpClient.callUrlWithRetry(loginUrl)
        userId = self.__extractUserDetailsFromLogin(result)

        deviceIdUrl = f'{self.host}/getDeviceList?secToken={self.securityToken}&userId={userId}&timestamp={self.__getDate()}'
        result = await httpClient.callUrlWithRetry(deviceIdUrl)
        return self.__extractGatewayDeviceId(result)

    async def __requestDevices(self):
        url = f'{self.host}/setMultiDeviceAttributes2?secToken={self.securityToken}&devId={self.gatewayDeviceId}&name1=B01&value1=5&timestamp={self.__getDate()}'  
        await self.__fetchUrlWithLoginRetry(url)
        
        url = f'{self.host}/getDeviceAttributesWithValues?secToken={self.securityToken}&devId={self.gatewayDeviceId}&deviceTypeId=1&timestamp={self.__getDate()}'  
        responseContent = await self.__fetchUrlWithLoginRetry(url)
        return self.__extractDeviceInfo(responseContent)

    async def __setPreset(self, deviceId, stateName):
        payload = urllib.parse.quote(f'!{deviceId}{chr(int(RUN_MODES.index(stateName.upper()) + 35))}')
        url = f'{self.host}/setMultiDeviceAttributes2?secToken={self.securityToken}&devId={self.gatewayDeviceId}&name1=B05&value1={payload}&timestamp={self.__getDate()}'
        result = await self.__fetchUrlWithLoginRetry(url)
        self.__validateOperationResponse(result)

    async def __setTemprature(self, deviceId, temperature):
        payload = urllib.parse.quote(f'!{deviceId}{chr(int(temperature * 2 + 32))}')
        url = f'{self.host}/setMultiDeviceAttributes2?secToken={self.securityToken}&devId={self.gatewayDeviceId}&name1=B06&value1={payload}&timestamp={self.__getDate()}'
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

    def __extractDeviceInfo(self, response):
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

            sumaries = []
            summaryValue = list(filter(lambda item: item.get('Id') == '2257', items))[0].get('Value')
            for element in [summaryValue[i:i+8] for i in range(0, len(summaryValue), 8)]:
                if(len(element) == 8):
                    sumaries.append({ 
                        'Id': element[0:4], 
                        'Summary': element[4:] 
                    })
        
            thermostats = []
            for element in list(filter(lambda item: item.get('Id') == '2287', items))[0].get('Value').split(','):
                if(len(element) > 4):
                    id = element[0:4]
                    summary = list(filter(lambda item: item.get('Id') == id, sumaries))[0].get('Summary')

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

    def __validateOperationResponse(self, response):
        tree = ET.fromstring(response)
        responseCode = tree.find('retCode')
        if responseCode.text != '0':
            raise Exception('Operation failed; unexpected response code.\n{response}')