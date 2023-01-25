import aiohttp
import time
import logging

_LOGGER = logging.getLogger(__name__)

async def callUrlWithRetry(url, attempts = 3):
    for attempt in range(attempts):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'{url}') as response:
                    if response.status == 200:
                        return await response.text()
                    
                    _LOGGER.warn(f'Calling "{url}" resulted in status code "{response.status}" on attempt "{attempt}".')
                    time.sleep(attempts)
        except Exception as e:
            _LOGGER.error(f'Unexpected error calling URL "{url}"; message: {e}')
    
    raise Exception(f'Failed to call URL "{url}" after "{attempts}" attempts.')