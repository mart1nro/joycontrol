import logging
import pathlib
import uuid
import weakref

import dbus_next
from dbus_next import BusType

from joycontrol import utils
from joycontrol.bluetooth_proxy.exceptions import RegisterException

logger = logging.getLogger(__name__)
HID_UUID = '00001124-0000-1000-8000-00805f9b34fb'
HID_PATH = '/bluez/switch/hid'

BLUEZ_PATH = "/org/bluez"
BLUEZ_BUS_NAME = "org.bluez"
BLUEZ_ADAPTER_INTERFACE = f"{BLUEZ_BUS_NAME}.Adapter1"
BLUEZ_PROFILE_INTERFACE = f"{BLUEZ_BUS_NAME}.ProfileManager1"
BLUEZ_DEVICE_INTERFACE = f"{BLUEZ_BUS_NAME}.Device1"


class HidDevice:

    def __init__(self, bus: dbus_next.aio.MessageBus, adapter: dbus_next.aio.ProxyInterface):
        self._bus = bus
        self._adapter = adapter
        self._finalizer = weakref.finalize(self, self._bus.disconnect)

    @classmethod
    async def create(cls, device_id=None):
        bus = await dbus_next.aio.MessageBus(bus_type=BusType.SYSTEM).connect()
        bluez_nodes = await bus.introspect(BLUEZ_BUS_NAME, BLUEZ_PATH)
        blues_proxy = bus.get_proxy_object(BLUEZ_BUS_NAME, BLUEZ_PATH, bluez_nodes)
        for adapter_path in blues_proxy.child_paths:
            adapter_nodes = await bus.introspect(BLUEZ_BUS_NAME, adapter_path)
            adapter_object = bus.get_proxy_object(BLUEZ_BUS_NAME, adapter_path, adapter_nodes)
            try:
                adapter = adapter_object.get_interface(BLUEZ_ADAPTER_INTERFACE)
            except Exception as e:
                logger.info("Skipping %s: %s", adapter_path, e)
            else:
                if device_id is None \
                        or await adapter.get_address() == device_id \
                        or adapter_path.endswith(str(device_id)):
                    return cls(bus, adapter)
        raise ValueError(f'Adapter {device_id} not found.')

    async def get_address(self) -> str:
        """
        :return: adapter Bluetooth address
        """
        return await self._adapter.get_address()

    async def powered(self, boolean=True):
        await self._adapter.set_powered(boolean)

    async def discoverable(self, boolean=True):
        """
        Make adapter discoverable, starts advertising.
        """
        await self._adapter.set_discoverable(boolean)

    async def pairable(self, boolean=True):
        """
        Make adapter pairable
        """
        await self._adapter.set_pairable(boolean)

    async def set_class(self, cls='0x002508'):
        """
        Sets Bluetooth device class. Requires hciconfig system command.
        :param cls: default 0x002508 (Gamepad/joystick device class)
        """
        logger.info(f'setting device class to {cls}...')
        await utils.run_system_command(f'hciconfig {await self._adapter.get_name()} class {cls}')

    async def set_name(self, name: str):
        """
        Set Bluetooth device name.
        :param name: to set.
        """
        logger.info(f'setting device name to {name}...')
        await self._adapter.set_alias(name)

    async def register_sdp_record(self, record_path):
        _uuid = str(uuid.uuid4())

        opts = {
            'ServiceRecord': dbus_next.Variant("s", pathlib.Path(record_path).read_text()),
            'Role': dbus_next.Variant("s", 'server'),
            'Service': dbus_next.Variant("s", HID_UUID),
            'RequireAuthentication': dbus_next.Variant("b", False),
            'RequireAuthorization': dbus_next.Variant("b", False)
        }
        try:
            profile_introspection = await self._bus.introspect(BLUEZ_BUS_NAME, BLUEZ_PATH)
            profile_proxy = self._bus.get_proxy_object(BLUEZ_BUS_NAME, BLUEZ_PATH, profile_introspection)
            profile_interface = profile_proxy.get_interface(BLUEZ_PROFILE_INTERFACE)
            await profile_interface.call_register_profile(HID_PATH, _uuid, opts)
        except dbus_next.errors.DBusError as dbus_err:
            raise RegisterException("Already registered") from dbus_err

        return _uuid
