import asyncio
import logging
import struct
import time
from typing import Any

from joycontrol.report import InputReport

logger = logging.getLogger(__name__)


class L2CAP_Transport(asyncio.Transport):
    def __init__(self, loop, protocol, l2cap_socket, read_buffer_size, capture_file=None) -> None:
        self._loop = loop
        self._protocol = protocol

        self._sock = l2cap_socket
        self._read_buffer_size = read_buffer_size

        self._extra_info = {
            'peername': self._sock.getpeername(),
            'sockname': self._sock.getsockname()
        }

        self._read_thread = asyncio.ensure_future(self._read())

        self._is_closing = False
        self._is_reading = asyncio.Event()
        self._is_reading.set()

        self._input_report_timer = 0x00

        self._capture_file = capture_file

    async def _read(self):
        while True:
            await self._is_reading.wait()

            data = await self._loop.sock_recv(self._sock, self._read_buffer_size)

            if self._capture_file is not None:
                # write data to log file
                _time = struct.pack('d', time.time())
                size = struct.pack('i', len(data))
                self._capture_file.write(_time + size + data)

            #logger.debug(f'received "{list(data)}"')
            await self._protocol.report_received(data, self._sock.getpeername())

    def is_reading(self) -> bool:
        return self._is_reading.is_set()

    def pause_reading(self) -> None:
        self._is_reading.clear()

    def resume_reading(self) -> None:
        self._is_reading.set()

    def set_read_buffer_size(self, size):
        self._read_buffer_size = size

    async def write(self, data: Any) -> None:
        if isinstance(data, bytes):
            _bytes = data
        elif isinstance(data, InputReport):
            # set timer byte of input report
            data.set_timer(self._input_report_timer)
            self._input_report_timer = (self._input_report_timer + 1) % 256
            _bytes = bytes(data)
        else:
            raise ValueError('data must be bytes or InputReport')

        if self._capture_file is not None:
            # write data to log file
            _time = struct.pack('d', time.time())
            size = struct.pack('i', len(_bytes))
            self._capture_file.write(_time + size + _bytes)

        #logger.debug(f'sending "{_bytes}"')
        await self._loop.sock_sendall(self._sock, _bytes)

    def abort(self) -> None:
        super().abort()

    def get_extra_info(self, name: Any, default=None) -> Any:
        return self._extra_info.get(name, default)

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
