import asyncio
import logging
import struct
import time
import socket
import math
from typing import Any
from contextlib import suppress

from joycontrol import utils
from joycontrol.my_semaphore import MyBoundedSemaphore

logger = logging.getLogger(__name__)


class NotConnectedError(ConnectionResetError):
    pass

class L2CAP_Transport(asyncio.Transport):
    def __init__(self, loop, protocol, itr_sock, ctr_sock, read_buffer_size, capture_file=None, flow_control = 4) -> None:
        super(L2CAP_Transport, self).__init__()

        self._loop = loop
        self._protocol = protocol

        self._itr_sock = itr_sock
        self._ctr_sock = ctr_sock

        self._capture_file = capture_file

        self._extra_info = {
            'peername': self._itr_sock.getpeername(),
            'sockname': self._itr_sock.getsockname(),
            'socket': self._itr_sock
        }

        self._is_closing = False

        # writing control
        self._write_lock = asyncio.Event()
        self._write_lock.set()
        self._write_lock_thread = utils.start_asyncio_thread(self._write_lock_monitor(), ignore=asyncio.CancelledError)
        self._write_window = MyBoundedSemaphore(flow_control)
        self._write_window_thread = utils.start_asyncio_thread(self._write_window_monitor(), ignore=asyncio.CancelledError)

        # reading control
        self._read_buffer_size = read_buffer_size
        self._is_reading = asyncio.Event()
        self._is_reading.set()
        self._read_thread = utils.start_asyncio_thread(self._reader(), ignore=asyncio.CancelledError)

    async def _write_window_monitor(self):
        with socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI) as hci:
            hci.bind((0,))
            hci.setblocking(False)
            # 0x04 = HCI_EVT; 0x13 = Number of completed packets
            hci.setsockopt(socket.SOL_HCI, socket.HCI_FILTER, struct.pack("IIIh2x", 1 << 0x04, (1 << 0x13), 0, 0))

            while True:
                data = await self._loop.sock_recv(hci, 10)
                self._write_window.release(data[6] + data[7] * 0x100, best_effort=True)

    async def _write_lock_monitor(self):
        with socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI) as hci:
            hci.bind((0,))
            hci.setblocking(False)
            # 0x04 = HCI_EVT; 0x1b = Max Slots Change
            hci.setsockopt(socket.SOL_HCI, socket.HCI_FILTER, struct.pack("IIIh2x", 1 << 0x04, (1 << 0x1b), 0, 0))
            while True:
                data = await self._loop.sock_recv(hci, 10)
                if data[5] < 5:
                    self.pause_writing()
                    await asyncio.sleep(1)
                    self.resume_writing()

    async def _reader(self):
        while True:
            await self._protocol.report_received(await self.read(), self._itr_sock.getpeername())

    async def read(self):
        """
        Read data from the underlying socket. This function waits,
        if reading is paused using the pause_reading function.

        :returns bytes
        """
        await self._is_reading.wait()
        data = await self._loop.sock_recv(self._itr_sock, self._read_buffer_size)

        # logger.debug(f'received "{list(data)}"')

        if not data:
            # disconnect happened
            logger.error('No data received.')
            self._protocol.connection_lost()

        if self._capture_file is not None:
            # write data to log file
            _time = struct.pack('d', time.time())
            size = struct.pack('i', len(data))
            self._capture_file.write(_time + size + data)

        return data

# Base transport API

    def write_eof():
        raise NotImplementedError("cannot write EOF")

    def get_extra_info(self, name: Any, default=None) -> Any:
        return self._extra_info.get(name, default)

    def is_closing(self) -> bool:
        return self._is_closing

    def set_protocol(self, protocol: asyncio.BaseProtocol) -> None:
        self._protocol = protocol

    def get_protocol(self) -> asyncio.BaseProtocol:
        return self._protocol

# Read-Transport API

    def is_reading(self) -> bool:
        """
        :returns True if the reader is running
        """
        return self._reader is not None and self._is_reading.is_set()

    def pause_reading(self) -> None:
        """
        Pauses any 'read' function calls.
        """
        self._is_reading.clear()

    def resume_reading(self) -> None:
        """
        Resumes all 'read' function calls.
        """
        self._is_reading.set()

    def set_read_buffer_size(self, size):
        self._read_buffer_size = size

# Write-Transport API:
# This is not compliant to the official trasnport API, as the core methods
# are asnyc. This is because the official API has no control over time and
# imho is quite lacking...

    def abort():
        raise NotImplementedError()

    def can_write_eof():
        return False

    def get_write_buffer_size():
        return self._write_window.get_aquired()

    def get_write_buffer_limits():
        return (0, self._write_window.get_limit())

    def set_write_buffer_limits(high=None, low=None):
        if low:
            raise NotImplementedError("Cannot set a lower bound for in flight data...")

        self._write_window.set_limit(high)

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

        # logger.debug(f'sending "{_bytes}"')

        try:
            await self._write_window.acquire()
            await self._write_lock.wait()
            await self._loop.sock_sendall(self._itr_sock, _bytes)
        except OSError as err:
            logger.error(err)
            self._protocol.connection_lost()
        except ConnectionResetError as err:
            logger.error(err)
            self._protocol.connection_lost()

    async def writelines(*data):
        for d in data:
            await self.write(data)

    def pause_writing(self):
        logger.info("pause transport write")
        self._write_lock.clear()

    def resume_writing(self):
        logger.info("resume transport write")
        self._write_lock.set()

    def is_writing(self):
        return not self._write_lock.is_set()

    async def close(self):
        """
        Stops reader and closes underlying socket
        """
        if not self._is_closing:
            # was not already closed
            self._is_closing = True

            self.pause_reading()
            self.pause_writing()

            self._read_thread.cancel()
            self._write_lock_thread.cancel()
            self._write_window_thread.cancel()

            with suppress(asyncio.CancelledError):
                await self._read_thread
            with suppress(asyncio.CancelledError):
                await self._write_lock_thread
            with suppress(asyncio.CancelledError):
                await self._write_window_thread

            # interrupt connection should be closed first
            self._itr_sock.close()
            self._ctr_sock.close()

            self._protocol.connection_lost(None)
