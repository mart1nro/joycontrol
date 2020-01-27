import asyncio
import enum
import logging
import socket
import uuid
from asyncio import BaseTransport, BaseProtocol, Transport
from typing import Optional, Union, Tuple, Text, Any

import dbus

import logging_default as log

logger = logging.getLogger(__name__)


class L2CAP_Transport(Transport):
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

    def set_protocol(self, protocol: BaseProtocol) -> None:
        self._protocol = protocol

    def get_protocol(self) -> BaseProtocol:
        return self._protocol


class Controller(enum.Enum):
    JOYCON_L = 0x01
    JOYCON_R = 0x02
    PRO_CONTROLLER = 0x03

    def device_name(self):
        """
        :returns corresponding bluetooth device name
        """
        if self == Controller.JOYCON_L:
            return 'Joy-Con (L)'
        elif self == Controller.JOYCON_R:
            return 'Joy-Con (R)'
        elif self == Controller.PRO_CONTROLLER:
            return 'Pro Controller'
        else:
            raise NotImplementedError()


def controller_protocol_factory(controller: Controller):
    def create_controller_protocol():
        return ControllerProtocol(controller)
    return create_controller_protocol


class ControllerProtocol(BaseProtocol):
    def __init__(self, controller: Controller):
        self.transport = None

    def connection_made(self, transport: BaseTransport) -> None:
        logger.debug('Connection established.')
        self.transport = transport

    def connection_lost(self, exc: Optional[Exception]) -> None:
        raise NotImplementedError()

    async def report_received(self, data: Union[bytes, Text], addr: Tuple[str, int]) -> None:
        raise NotImplementedError()

    def error_received(self, exc: Exception) -> None:
        raise NotImplementedError()


async def run_system_command(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    logger.debug(f'[{cmd!r} exited with {proc.returncode}]')
    if stdout:
        logger.debug(f'[stdout]\n{stdout.decode()}')
    if stderr:
        logger.debug(f'[stderr]\n{stderr.decode()}')

    return proc.returncode


class HidDevice:
    _HID_UUID = '00001124-0000-1000-8000-00805f9b34fb'
    _HID_PATH = '/bluez/switch/hid'

    PRO_CONTROLLER = 'Pro Controller'
    JOYCON_R = 'Joy-Con (R)'
    JOYCON_L = 'Joy-Con (L)'

    def __init__(self):
        self._uuid = str(uuid.uuid4())

        # Setting up dbus to advertise the service record
        bus = dbus.SystemBus()
        obj = bus.get_object('org.bluez', '/org/bluez/hci0')
        self.adapter = dbus.Interface(obj, 'org.bluez.Adapter1')
        self.properties = dbus.Interface(self.adapter, 'org.freedesktop.DBus.Properties')

    def discoverable(self, boolean=True):
        #self.properties.Set(self.adapter.dbus_interface, 'Powered', True)
        self.properties.Set(self.adapter.dbus_interface, 'Discoverable', boolean)

    async def set_class(self, cls=0x002508):
        """
        :param cls: default 0x002508 (Gamepad/joystick device class)
        """
        logger.info(f'setting device class to {cls}...')
        await run_system_command(f'hciconfig hci0 class {cls}')

    async def set_name(self, name: str):
        logger.info(f'setting device name to {name}...')
        await run_system_command(f'hciconfig hci0 name "{name}"')

    def register_sdp_record(self, record_path):
        with open(record_path) as record:
            opts = {
                'ServiceRecord': record.read(),
                'Role': 'server',
                'Service': self._HID_UUID,
                'RequireAuthentication': False,
                'RequireAuthorization': False
            }
            bus = dbus.SystemBus()
            manager = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), "org.bluez.ProfileManager1")
            manager.RegisterProfile(self._HID_PATH, self._uuid, opts)


async def create_hid_server(protocol_factory, ctl_psm, itr_psm):
    ctl_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    itr_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)

    # for some reason we need to restart bluetooth here, the Switch does not connect to the sockets if we don't...
    logger.info('Restarting bluetooth service...')
    await run_system_command('systemctl restart bluetooth.service')
    await asyncio.sleep(1)

    ctl_sock.setblocking(False)
    itr_sock.setblocking(False)

    ctl_sock.bind((socket.BDADDR_ANY, ctl_psm))
    itr_sock.bind((socket.BDADDR_ANY, itr_psm))

    ctl_sock.listen(1)
    itr_sock.listen(1)

    hid = HidDevice()
    # setting bluetooth adapter name and class to the device we wish to emulate
    await hid.set_name(HidDevice.JOYCON_L)
    await hid.set_class()

    logger.info('Advertising the Bluetooth SDP record...')
    hid.register_sdp_record('profile/sdp_record_hid_pro.xml')
    hid.discoverable()

    loop = asyncio.get_event_loop()
    client_ctl, address = await loop.sock_accept(ctl_sock)
    logger.info(f'Accepted connection at psm {ctl_psm} from {address}')
    client_itr, address = await loop.sock_accept(itr_sock)
    logger.info(f'Accepted connection at psm {itr_psm} from {address}')

    protocol = protocol_factory()
    transport = L2CAP_Transport(asyncio.get_event_loop(), protocol, client_itr, address, 50)
    protocol.connection_made(transport)

    return transport


async def send_empty_input_reports(transport):
    data = [0x00] * 50
    data[0] = 0xA1

    while True:
        await transport.write(bytes(data))
        await asyncio.sleep(1)


async def main():
    transport = await create_hid_server(controller_protocol_factory(Controller.JOYCON_L), 17, 19)

    future = asyncio.ensure_future(send_empty_input_reports(transport))

    await asyncio.sleep(10)

    future.cancel()
    try:
        await future
    except asyncio.CancelledError:
        pass

    await transport.close()


if __name__ == '__main__':
    # setup logging
    log.configure()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
