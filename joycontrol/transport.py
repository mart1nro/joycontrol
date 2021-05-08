import asyncio
import logging
import struct
import time
import socket
from typing import Any

from joycontrol import utils

logger = logging.getLogger(__name__)


class NotConnectedError(ConnectionResetError):
    pass

class L2CAP_Transport(asyncio.Transport):
    def __init__(self, loop, protocol, itr_sock, ctr_sock, read_buffer_size, capture_file=None, flow_control = 10) -> None:
        #TODO: dynamic flow control. Higher values cause less stuttering but the anticipare_max_slots might break
        super(L2CAP_Transport, self).__init__()

        self._loop = loop
        self._protocol = protocol

        self._itr_sock = itr_sock
        self._ctr_sock = ctr_sock

        self._read_buffer_size = read_buffer_size

        if flow_control:
            self._flow_control_init(flow_control)

        self._extra_info = {
            'peername': self._itr_sock.getpeername(),
            'sockname': self._itr_sock.getsockname(),
            'socket': self._itr_sock
        }

        self._is_closing = False
        self._is_reading = asyncio.Event()

        self._capture_file = capture_file

        # start underlying reader
        self._is_reading.set()
        self._read_thread = utils.start_asyncio_thread(self._reader(), ignore=asyncio.CancelledError)

# flow control

    async def _flow_monitor(self):
        hci = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
        hci.bind((0,))
        hci.setblocking(False)
        # 0x04 = HCI_EVT; 0x13 = Number of completed packets
        hci.setsockopt(socket.SOL_HCI, socket.HCI_FILTER, struct.pack("IIIh2x", 1 << 0x04, (1 << 0x13), 0, 0))

        while True:
            data = await self._loop.sock_recv(hci, 10)
            #print(f"flow ctl: {self._pending_packets._value}, releasing {data[6] + data[7] * 0x100}")
            for _ in range(data[6] + data[7] * 0x100):
                self._flow_window.release()

    async def _lock_monitor(self):
        hci = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
        hci.bind((0,))
        hci.setblocking(False)
        hci.setsockopt(socket.SOL_HCI, socket.HCI_FILTER, struct.pack("IIIh2x", 1 << 0x04, (1 << 0x1b), 0, 0))
        while True:
            data = await self._loop.sock_recv(hci, 10)
            if data[5] < 5:
                self._flow_control_lock()
                await asyncio.sleep(1)
                self._flow_control_unlock()

    def _flow_control_init(self, flow_control):
        self._flow_control = bool(flow_control)
        if flow_control:
            self._flow_lock = asyncio.Event()
            self._flow_lock.set()

            self._flow_window = asyncio.Semaphore(flow_control)

            self._flow_control_monitor = utils.start_asyncio_thread(self._flow_monitor(), ignore=asyncio.CancelledError)
            self._lock_control_monitor = utils.start_asyncio_thread(self._lock_monitor(), ignore=asyncio.CancelledError)

    async def _flow_control_send(self):
        if self._flow_control:
            await self._flow_window.acquire()
            await self._flow_lock.wait()

    def _flow_control_lock(self):
        if self._flow_control:
            logger.info("transport lock")
            self._flow_lock.clear()

    def _flow_control_unlock(self):
        if self._flow_control:
            logger.info("transport unlock")
            self._flow_lock.set()

    async def _flow_control_deinit(self):
        if self._flow_control:
            self._flow_control_monitor.cancel()
            self._lock_control_monitor.cancel()

            try:
                await self._flow_control_monitor
                await self._lock_control_monitor
            except asyncio.CancelledError:
                pass

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
            raise NotConnectedError('No data received.')

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
            await self._flow_control_send()
            await self._loop.sock_sendall(self._itr_sock, _bytes)
        except OSError as err:
            logger.error(err)
            self._protocol.connection_lost()
            raise NotConnectedError(err)
        except ConnectionResetError as err:
            logger.error(err)
            self._protocol.connection_lost()
            raise err

    def abort(self) -> None:
        raise NotImplementedError

    def get_extra_info(self, name: Any, default=None) -> Any:
        return self._extra_info.get(name, default)

    def is_closing(self) -> bool:
        return self._is_closing

    async def close(self):
        """
        Stops reader and closes underlying socket
        """
        if not self._is_closing:
            # was not already closed
            self._is_closing = True
            self._read_thread.cancel()
            await self._flow_control_deinit()

            try:
                await self._read_thread
                await self._flow_control_monitor
            except asyncio.CancelledError:
                pass

            # interrupt connection should be closed first
            self._itr_sock.close()
            self._ctr_sock.close()

    def set_protocol(self, protocol: asyncio.BaseProtocol) -> None:
        self._protocol = protocol

    def get_protocol(self) -> asyncio.BaseProtocol:
        return self._protocol
