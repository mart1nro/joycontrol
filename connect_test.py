import logging
import os
import re
import subprocess
import time
import uuid
from enum import Enum, auto
from time import sleep
import logging_default as log

import bluetooth as blt
import dbus

logger = logging.getLogger(__name__)

# Defining the ports for the control and interrupt sockets
CTL_PSM = 17
ITR_PSM = 19


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

    def set_class(self, cls=0x002508):
        """
        :param cls: default 0x002508 (Gamepad/joystick device class)
        """
        logger.info(f'setting device class to {cls}...')
        subprocess.call(['hciconfig', 'hci0', 'class', str(cls)])

    def set_name(self, name: str):
        logger.info(f'setting device name to {name}...')
        subprocess.call(['hciconfig', 'hci0', 'name', name])

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


class InputReport:
    def __init__(self):
        self.m1 = [0xA1, 0x21, 0x05, 0x8E, 0x84, 0x00, 0x12, 0x01, 0x18, 0x80, 0x01, 0x18, 0x80, 0x80, 0x82, 0x02, 0x03, 0x48, 0x01, 0x02, 0xDC, 0xA6, 0x32, 0x71, 0x58, 0xBB, 0x01, 0x01]
        self.m2 = [0xA1, 0x21, 0x06, 0x8E, 0x84, 0x00, 0x12, 0x01, 0x18, 0x80, 0x01, 0x18, 0x80, 0x80, 0x80, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

    def create(self, message):
        miss = 49 - len(message)
        message = message + miss * [0x00]
        assert len(message) == 49
        return message


class InputReport2:
    def __init__(self):
        self.data = [0x00] * 50
        # all input reports are prepended with 0xA1
        self.data[0] = 0xA1

    def set(self, input_report_id, timer=0x00):
        self.data[1] = input_report_id
        self.data[2] = timer % 256
        # battery level + connection info
        self.data[3] = 0x8E

        # Todo: Button status, analog stick data, vibrator input

        # ACK byte for subcmd reply
        self.data[14] = 0x82

        # Reply-to subcommand ID
        self.data[14] = 0x02

    def sub_0x2_device_info(self, mac, fm_version=(0x03, 0x48), controller=0x01):
        """
        Sub command 0x02 request device info response.

        :param mac: Controller MAC address in Big Endian (6 Bytes)
        :param fm_version: TODO
        :param controller: 1=Left Joy-Con, 2=Right Joy-Con, 3=Pro Controller
        """
        if len(fm_version) != 2:
            raise ValueError('Firmware version must consist of 2 bytes!')
        elif len(mac) != 6:
            raise ValueError('Bluetooth mac address must consist of 6 bytes!')

        # reply to sub command ID
        self.data[14] = 0x02

        # sub command reply data
        offset = 15
        self.data[offset: offset + 1] = fm_version
        self.data[offset + 2] = controller
        self.data[offset + 3] = 0x02
        self.data[offset + 4: offset + 9] = mac
        self.data[offset + 10] = 0x01
        self.data[offset + 11] = 0x01

    def __bytes__(self):
        return bytes(self.data)


class SubCommand(Enum):
    REQUEST_DEVICE_INFO = auto()
    NOT_IMPLEMENTED = auto()


class OutputReport:
    def __init__(self, data):
        if data[0] != 0xA2:
            raise ValueError('Output reports must start with 0xA2')
        self.data = data

    def sub_command(self):
        if self.data[11] == 0x02:
            return SubCommand.REQUEST_DEVICE_INFO
        else:
            return None

    def __bytes__(self):
        return bytes(self.data)


def get_bt_mac_address(dev=0):
    output = subprocess.check_output(['hciconfig', f'hci{dev}'], encoding='UTF-8')
    match = re.search(r'BD Address: (?P<mac>\w\w:\w\w:\w\w:\w\w:\w\w:\w\w)', output)
    if match:
        return list(map(lambda x: int(x, 16), match.group('mac').split(':')))
    else:
        raise ValueError(f'BD Address not found in "{output}"')


def pair_switch(client_itr, own_bd_mac_address):
    while True:
        in_report = InputReport2()

        reply = None
        while reply is None:
            # It seems like we have to initiate the conversation, so send and empty input report
            client_itr.send(bytes(in_report))
            sleep(.1)
            try:
                reply = client_itr.recv(50)
            except blt.btcommon.BluetoothError as bt_err:
                print(bt_err)

        out_report = OutputReport(list(reply))

        # DEVIVCE INFO REQUEST
        sub_command = out_report.sub_command()
        if sub_command is None:
            logger.error(f'No sub command found in "{reply}"')
            continue
        elif sub_command == SubCommand.REQUEST_DEVICE_INFO:
            # send device info
            device_info_in_report = InputReport2()
            device_info_in_report.sub_0x2_device_info(own_bd_mac_address)

            logger.info('Sending device info...')
            client_itr.send(bytes(device_info_in_report))
        elif sub_command == SubCommand.NOT_IMPLEMENTED:
            logger.error(f'Sub command not implemented of "{reply}"')
            continue

        # awaiting Subcommand 0x08: Set shipment
        reply = None
        while reply is None:
            try:
                reply = client_itr.recv(50)
            except blt.btcommon.BluetoothError as bt_err:
                print(bt_err)
            sleep(.5)

        print(reply)

        return True
    return False


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='open bluetooth hid socket')
    # parser.add_argument('port', type=int, help='socket port')
    args = parser.parse_args()

    # setup logging
    log.configure()

    # check if root
    if not os.geteuid() == 0:
        raise PermissionError('Script must be run as root!')

    # Creating L2CAP sockets for control and interrupt channel
    ctl_sock = blt.BluetoothSocket(blt.L2CAP)
    itr_sock = blt.BluetoothSocket(blt.L2CAP)

    logger.info('Restarting bluetooth service...')
    os.system('systemctl restart bluetooth.service')
    time.sleep(1)

    logger.info(f'Binding control channel to {CTL_PSM}...')
    ctl_sock.bind(("", CTL_PSM))
    logger.info(f'Binding interrupt channel to {ITR_PSM}...')
    itr_sock.bind(("", ITR_PSM))

    logger.info('start listening on the server sockets')
    ctl_sock.listen(1)  # Limit of 1 connection
    itr_sock.listen(1)



    hid = HidDevice()
    # setting bluetooth adapter name and class to the device we wish to emulate
    hid.set_name(HidDevice.JOYCON_L)
    hid.set_class()

    logger.info('Advertising the Bluetooth SDP record...')
    hid.register_sdp_record('profile/sdp_record_hid_pro.xml')
    hid.discoverable()

    logger.info('Waiting for connection...')
    client_ctl, address = ctl_sock.accept()
    logger.info(f'Accepted connection at {CTL_PSM} from {address}')
    client_itr, address = itr_sock.accept()
    client_itr.settimeout(0)
    logger.info(f'Accepted connection at {ITR_PSM} from {address}')

    """
    data = [0] * 49
    data[0] = 0xA1

    hello = 0
    ip = InputReport()

    for i in range(100):
        logger.info(f'sending data {data}...')
        client_itr.send(bytes(data))

        try:
            print("received", client_itr.recv(49))
            hello += 1

        except blt.btcommon.BluetoothError as bt_err:
            print(bt_err)

        if hello == 1:
            data = ip.create(ip.m1)
            print("GO 1")
        elif hello == 2:
            data = ip.create(ip.m2)
            print("GO 2")

        sleep(0.5)
    """
    pair_switch(client_itr, get_bt_mac_address())

    itr_sock.close()
    ctl_sock.close()
