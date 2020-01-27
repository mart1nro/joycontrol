import logging
import uuid

import dbus

import utils

logger = logging.getLogger(__name__)


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
        await utils.run_system_command(f'hciconfig hci0 class {cls}')

    async def set_name(self, name: str):
        logger.info(f'setting device name to {name}...')
        await utils.run_system_command(f'hciconfig hci0 name "{name}"')

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