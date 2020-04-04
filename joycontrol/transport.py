import asyncio
import logging
import struct
import time
from typing import Any

from joycontrol import utils

logger = logging.getLogger(__name__)


class NotConnectedError(ConnectionResetError):
    pass


class L2CAP_Transport(asyncio.Transport):
    def __init__(self, loop, protocol, itr_sock, ctr_sock, read_buffer_size, capture_file=None) -> None:
        super(L2CAP_Transport, self).__init__()

        self._loop = loop
        self._protocol = protocol

        self._itr_sock = itr_sock
        self._ctr_sock = ctr_sock

        self._read_buffer_size = read_buffer_size

        self._extra_info = {
            'peername': self._itr_sock.getpeername(),
            'sockname': self._itr_sock.getsockname(),
            'socket': self._itr_sock
        }

        self._is_closing = False
        self._is_reading = asyncio.Event()

        self._capture_file = capture_file

        # start underlying reader
        self._read_thread = None
        self._is_reading.set()
        self.start_reader()

    async def _reader(self):
        while True:
            try:
                data = await self.read()
            except NotConnectedError:
                self._read_thread = None
                break

            #logger.debug(f'received "{list(data)}"')
            await self._protocol.report_received(data, self._itr_sock.getpeername())

    def start_reader(self):
        """
        Starts the transport reader which calls the protocols report_received function for every incoming message
        """
        if self._read_thread is not None:
            raise ValueError('Reader is already running.')

        self._read_thread = asyncio.ensure_future(self._reader())

        # Create callback in case the reader is failing
        callback = utils.create_error_check_callback(ignore=asyncio.CancelledError)
        self._read_thread.add_done_callback(callback)

    async def set_reader(self, reader: asyncio.Future):
        """
        Cancel the currently running reader and register the new one.
        A reader is a coroutine that calls this transports 'read' function.
        The 'read' function calls can be paused by calling pause_reading of this transport.
        :param reader: future reader
        """
        if self._read_thread is not None:
            # cancel currently running reader
            if self._read_thread.cancel():
                try:
                    await self._read_thread
                except asyncio.CancelledError:
                    pass

        # Create callback for debugging in case the reader is failing
        err_callback = utils.create_error_check_callback(ignore=asyncio.CancelledError)
        reader.add_done_callback(err_callback)

        self._read_thread = reader

    def get_reader(self):
        return self._read_thread

    async def read(self):
        """
        Read data from the underlying socket. This function waits,
        if reading is paused using the pause_reading function.

        :returns bytes
        """
        await self._is_reading.wait()
        data = await self._loop.sock_recv(self._itr_sock, self._read_buffer_size)

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

        #logger.debug(f'sending "{_bytes}"')
        try:
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
            if self._read_thread.cancel():
                # wait for reader to cancel
                try:
                    await self._read_thread
                except asyncio.CancelledError:
                    pass

            # interrupt connection should be closed first
            self._itr_sock.close()
            self._ctr_sock.close()

    def set_protocol(self, protocol: asyncio.BaseProtocol) -> None:
        self._protocol = protocol

    def get_protocol(self) -> asyncio.BaseProtocol:
        return self._protocol
