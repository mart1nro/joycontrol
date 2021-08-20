import logging
import uuid
import dbus

from joycontrol import utils

logger = logging.getLogger(__name__)


HID_UUID = '00001124-0000-1000-8000-00805f9b34fb'
HID_PATH = '/bluez/switch/hid'


class HidDevice:
    def __init__(self, device_id=None):
        self._device_id = device_id
        bus = dbus.SystemBus()
        # Get Bluetooth adapter from dbus interface
        for path, ifaces in bus.get_object('org.bluez', '/').GetManagedObjects(dbus_interface='org.freedesktop.DBus.ObjectManager').items():
            adapter_info = ifaces.get('org.bluez.Adapter1')
            if adapter_info and (device_id is None or device_id == adapter_info['Address'] or path.endswith(str(device_id))):
                self.dev = bus.get_object('org.bluez', path)
                break
        else:
            raise ValueError(f'Adapter {device_id} not found.')

        self.adapter = dbus.Interface(self.dev, 'org.bluez.Adapter1')
        # The sad news is someone decided that this convoluted mess passing
        # strings back and forth to get properties would be simpler than literal
        # adapter.some_property = 4 or adapter.some_property_set(4)
        self.properties = dbus.Interface(self.dev, 'org.freedesktop.DBus.Properties')
        self._adapter_name = self.dev.object_path.split("/")[-1]

    def get_address(self) -> str:
        """
        :returns adapter Bluetooth address
        """
        return str(self.properties.Get(self.adapter.dbus_interface, "Address"))

    async def set_address(self, bt_addr, interactive=True):
        if not interactive:
            return False
        # TODO: automated detection
        print(f"Attempting to change the bluetooth MAC to {bt_addr}")
        print("please choose your method:")
        print("\t1: bdaddr - ericson, csr, TI, broadcom, zeevo, st")
        print("\t2: hcitool - intel chipsets")
        print("\t3: hcitool - cypress (raspberri pi 3B+ & 4B)")
        print("\tx: abort, dont't change")
        hci_version = " ".join(reversed(list(map(lambda h: '0x' + h, bt_addr.split(":")))))
        c = input()
        if c == '1':
            await utils.run_system_command(f'bdaddr -i {self._adapter_name} {bt_addr}')
        elif c == '2':
            await utils.run_system_command(f'hcitool cmd 0x3f 0x0031 {hci_version}')
        elif c == '3':
            await utils.run_system_command(f'hcitool cmd 0x3f 0x001 {hci_version}')
        else:
            return False
        await utils.run_system_command("hciconfig hci0 reset")
        await utils.run_system_command("systemctl restart bluetooth.service")

        # now we have to reget all dbus-shenanigans because we just restarted it's service.
        self.__init__(self._device_id)

        if self.get_address() != bt_addr:
            logger.info("Failed to set btaddr")
            return False
        else:
            logger.info(f"Changed bt_addr to {bt_addr}")
            return True

    def get_paired_switches(self):
        switches = []
        for path, ifaces in dbus.SystemBus().get_object('org.bluez', '/').GetManagedObjects('org.freedesktop.DBus.ObjectManager', dbus_interface='org.freedesktop.DBus.ObjectManager').items():
            d = ifaces.get("org.bluez.Device1")
            if d and d['Name'] == "Nintendo Switch":
                switches += [path]
        return switches

    def unpair_path(self, path):
        self.adapter.RemoveDevice(path)

    def powered(self, boolean=True):
        self.properties.Set(self.adapter.dbus_interface, 'Powered', boolean)

    def discoverable(self, boolean=True):
        """
        Make adapter discoverable, starts advertising.
        """
        self.properties.Set(self.adapter.dbus_interface, 'Discoverable', boolean)

    def pairable(self, boolean=True):
        """
        Make adapter pairable
        """
        self.properties.Set(self.adapter.dbus_interface, 'Pairable', boolean)

    async def set_class(self, cls='0x002508'):
        """
        Sets Bluetooth device class. Requires hciconfig system command.
        :param cls: default 0x002508 (Gamepad/joystick device class)
        """
        logger.info(f'setting device class to {cls}...')
        await utils.run_system_command(f'hciconfig {self._adapter_name} class {cls}')
        if self.properties.Get(self.adapter.dbus_interface, "Class") != int(cls, base=0):
            logger.error(f"Could not set class to the required {cls}. Connecting probably won't work.")

    async def set_name(self, name: str):
        """
        Set Bluetooth device name.
        :param name: to set.
        """
        logger.info(f'setting device name to {name}...')
        self.properties.Set(self.adapter.dbus_interface, 'Alias', name)

    def get_UUIDs(self):
        return self.properties.Get(self.adapter.dbus_interface, "UUIDs")

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

    @staticmethod
    def get_address_of_paired_path(path):
        return str(dbus.SystemBus().get_object('org.bluez', path).Get('org.bluez.Device1', "Address", dbus_interface='org.freedesktop.DBus.Properties'))
