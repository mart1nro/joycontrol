import logging
import uuid
import dbus

from joycontrol import utils

logger = logging.getLogger(__name__)


HID_UUID = '00001124-0000-1000-8000-00805f9b34fb'
HID_PATH = '/bluez/switch/hid'


class HidDevice:
    def __init__(self, device_id=None):
        bus = dbus.SystemBus()

        # Get Bluetooth adapter from dbus interface
        manager = dbus.Interface(bus.get_object('org.bluez', '/'), 'org.freedesktop.DBus.ObjectManager')
        for path, ifaces in manager.GetManagedObjects().items():
            adapter_info = ifaces.get('org.bluez.Adapter1')
            if adapter_info is None:
                continue
            elif device_id is None or device_id == adapter_info['Address'] or path.endswith(str(device_id)):
                obj = bus.get_object('org.bluez', path)
                self.adapter = dbus.Interface(obj, 'org.bluez.Adapter1')
                self.address = adapter_info['Address']
                self._adapter_name = path.split('/')[-1]

                self.properties = dbus.Interface(self.adapter, 'org.freedesktop.DBus.Properties')
                break
        else:
            raise ValueError(f'Adapter {device_id} not found.')

    def get_address(self) -> str:
        """
        :returns adapter Bluetooth address
        """
        return self.address

    def powered(self, boolean=True):
        self.properties.Set(self.adapter.dbus_interface, 'Powered', boolean)

    def discoverable(self, boolean=True):
        """
        Make adapter discoverable, starts advertising.
        """
        self.properties.Set(self.adapter.dbus_interface, 'Discoverable', boolean)

    async def set_class(self, cls='0x002508'):
        """
        Sets Bluetooth device class. Requires hciconfig system command.
        :param cls: default 0x002508 (Gamepad/joystick device class)
        """
        logger.info(f'setting device class to {cls}...')
        await utils.run_system_command(f'hciconfig {self._adapter_name} class {cls}')

    async def set_name(self, name: str):
        """
        Set Bluetooth device name.
        :param name: to set.
        """
        logger.info(f'setting device name to {name}...')
        self.properties.Set(self.adapter.dbus_interface, 'Alias', name)

    @staticmethod
    def register_sdp_record(record_path):
        _uuid = str(uuid.uuid4())

        with open(record_path) as record:
            opts = {
                'ServiceRecord': record.read(),
                'Role': 'server',
                'Service': HID_UUID,
                'RequireAuthentication': False,
                'RequireAuthorization': False
            }
            bus = dbus.SystemBus()
            manager = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), "org.bluez.ProfileManager1")
            manager.RegisterProfile(HID_PATH, _uuid, opts)

        return _uuid
