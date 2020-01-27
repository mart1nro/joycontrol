import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class L2CAP_Transport(asyncio.Transport):
    def __init__(self, loop, protocol, l2cap_socket, client_addr, read_buffer_size) -> None:
        self._loop = loop
        self._protocol = protocol

        self._sock = l2cap_socket
        self._client_addr = client_addr
        self._read_buffer_size = read_buffer_size

        self._read_thread = asyncio.ensure_future(self._read())

        self._is_closing = False
        self._is_reading = asyncio.Event()
        self._is_reading.set()

    async def _read(self):
        try:
            while True:

                await self._is_reading.wait()

                data = await self._loop.sock_recv(self._sock, self._read_buffer_size)
                logger.debug(f'received "{data}')
                await self._protocol.report_received(data, self._client_addr)
        except asyncio.CancelledError:
            # reading has been stopped
            pass

    def is_reading(self) -> bool:
        return self._is_reading.is_set()

    def pause_reading(self) -> None:
        self._is_reading.clear()

    def resume_reading(self) -> None:
        self._is_reading.set()

    def set_read_buffer_size(self, size):
        self._read_buffer_size = size

    def set_write_buffer_limits(self, high: int = ..., low: int = ...) -> None:
        super().set_write_buffer_limits(high, low)

    def get_write_buffer_size(self) -> int:
        return super().get_write_buffer_size()

    async def write(self, data: Any) -> None:
        logger.debug(f'sending "{data}"')
        await self._loop.sock_sendall(self._sock, data)

    def abort(self) -> None:
        super().abort()

    def get_extra_info(self, name: Any, default: Any = ...) -> Any:
        return super().get_extra_info(name, default)

    def is_closing(self) -> bool:
        return self._is_closing

    async def close(self):
        """
        Stops socket reader and closes socket
        """
        self._is_closing = True
        self._read_thread.cancel()
        # wait for reader to cancel
        try:
            await self._read_thread
        except asyncio.CancelledError:
            pass
        self._sock.close()

    def set_protocol(self, protocol: asyncio.BaseProtocol) -> None:
        self._protocol = protocol

    def get_protocol(self) -> asyncio.BaseProtocol:
        return self._protocol