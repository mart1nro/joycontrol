import asyncio

import hid

VENDOR_ID = 1406
PRODUCT_ID_JL = 8198
PRODUCT_ID_JR = 8199
PRODUCT_ID_PC = 8201


async def get_blt_hid_device():
    while True:
        for device in hid.enumerate(0, 0):
            # looking for devices matching Nintendo's vendor id and JoyCon product id
            if device['vendor_id'] == VENDOR_ID and device['product_id'] in (
            PRODUCT_ID_JL, PRODUCT_ID_JR, PRODUCT_ID_PC):
                return device

        await asyncio.sleep(2)


class AsyncHID(hid.Device):
    def __init__(self, *args, loop=asyncio.get_event_loop(), **kwargs):
        super().__init__(*args, **kwargs)
        self._loop = loop

        self._write_lock = asyncio.Lock()
        self._read_lock = asyncio.Lock()

    async def read(self, size, timeout=None):
        async with self._read_lock:
            return await self._loop.run_in_executor(None, hid.Device.read, self, size, timeout)

    async def write(self, data):
        async with self._write_lock:
            return await self._loop.run_in_executor(None, hid.Device.write, self, data)