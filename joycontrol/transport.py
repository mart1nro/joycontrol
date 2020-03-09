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
            'sockname': self._sock.getsockname(),
            'socket': self._sock
        }

        self._read_thread = asyncio.ensure_future(self._reader())

        # create callback to check for exceptions
        def callback(future):
            try:
                future.result()
            except Exception as err:
                logger.exception(err)

        self._read_thread.add_done_callback(callback)

        self._is_closing = False
        self._is_reading = asyncio.Event()
        self._is_reading.set()

        self._input_report_timer = 0x00

        self._capture_file = capture_file

    async def _reader(self):
        while True:
            await self._is_reading.wait()

            data = await self.read()

            #logger.debug(f'received "{list(data)}"')
            await self._protocol.report_received(data, self._sock.getpeername())

    async def read(self):
        data = await self._loop.sock_recv(self._sock, self._read_buffer_size)

        if self._capture_file is not None:
            # write data to log file
            _time = struct.pack('d', time.time())
            size = struct.pack('i', len(data))
            self._capture_file.write(_time + size + data)

        return data

    def is_reading(self) -> bool:
        """
        :returns True if the reader is running
        """
        return self._is_reading.is_set()

    def pause_reading(self) -> None:
        """
        Pauses the reader
        """
        self._is_reading.clear()

    def resume_reading(self) -> None:
        """
        Resumes the reader
        """
        self._is_reading.set()

    def set_read_buffer_size(self, size):
        self._read_buffer_size = size

    async def write(self, data: Any) -> None:
        if isinstance(data, bytes):
            _bytes = data
        else:
            _bytes = bytes(data)

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
