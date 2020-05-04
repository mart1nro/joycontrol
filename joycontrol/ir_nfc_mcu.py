import logging
from enum import Enum
from crc8 import crc8

logger = logging.getLogger(__name__)


class Action(Enum):
    NON = 0
    REQUEST_STATUS = 1
    START_TAG_POLLING = 2
    START_TAG_DISCOVERY = 3
    READ_TAG = 4
    READ_TAG_2 = 5
    READ_FINISHED = 6


class McuState(Enum):
    NOT_INITIALIZED = 0
    IRC = 1
    NFC = 2
    STAND_BY = 3
    BUSY = 4


def copyarray(dest, offset, src):
    for i in range(len(src)):
        dest[offset + i] = src[i]


class IrNfcMcu:
    """
    TODO: cleanup
    """

    def __init__(self):
        self._fw_major = [0, 3]
        self._fw_minor = [0, 5]

        self._bytes = [0] * 313

        self._action = Action.NON
        self._state = McuState.NOT_INITIALIZED

        self._nfc_content = None

    def get_fw_major(self):
        return self._fw_major

    def get_fw_minor(self):
        return self._fw_minor

    def set_action(self, v):
        self._action = v

    def get_action(self):
        return self._action

    def set_state(self, v):
        self._state = v

    def get_state(self):
        return self._state

    def _get_state_byte(self):
        if self.get_state() == McuState.NFC:
            return 4
        elif self.get_state() == McuState.BUSY:
            return 6
        elif self.get_state() == McuState.NOT_INITIALIZED:
            return 1
        elif self.get_state() == McuState.STAND_BY:
            return 1
        else:
            return 0

    def update_status(self):
        self._bytes[0] = 1
        self._bytes[1] = 0
        self._bytes[2] = 0
        self._bytes[3] = self._fw_major[0]
        self._bytes[4] = self._fw_major[1]
        self._bytes[5] = self._fw_minor[0]
        self._bytes[6] = self._fw_minor[1]
        self._bytes[7] = self._get_state_byte()

    def update_nfc_report(self):
        self._bytes = [0] * 313
        if self.get_action() == Action.REQUEST_STATUS:
            self.update_status()
        elif self.get_action() == Action.NON:
            self._bytes[0] = 0xff
        elif self.get_action() == Action.START_TAG_DISCOVERY:
            self._bytes[0] = 0x2a
            self._bytes[1] = 0
            self._bytes[2] = 5
            self._bytes[3] = 0
            self._bytes[4] = 0
            self._bytes[5] = 9
            self._bytes[6] = 0x31
            self._bytes[7] = 0
        elif self.get_action() == Action.START_TAG_POLLING:
            self._bytes[0] = 0x2a
            self._bytes[1] = 0
            self._bytes[2] = 5
            self._bytes[3] = 0
            self._bytes[4] = 0
            if self._nfc_content is not None:
                data = [0x09, 0x31, 0x09, 0x00, 0x00, 0x00, 0x01, 0x01, 0x02, 0x00, 0x07]
                copyarray(self._bytes, 5, data)
                copyarray(self._bytes, 5 + len(data), self._nfc_content[0:3])
                copyarray(self._bytes, 5 + len(data) + 3, self._nfc_content[4:8])
            else:
                logger.info('nfc content is none')
                self._bytes[5] = 9
                self._bytes[6] = 0x31
                self._bytes[7] = 0
        elif self.get_action() == Action.READ_TAG or self.get_action() == Action.READ_TAG_2:
            self._bytes[0] = 0x3a
            self._bytes[1] = 0
            self._bytes[2] = 7
            if self.get_action() == Action.READ_TAG:
                data1 = bytes.fromhex('010001310200000001020007')
                copyarray(self._bytes, 3, data1)
                copyarray(self._bytes, 3 + len(data1), self._nfc_content[0:3])
                copyarray(self._bytes, 3 + len(data1) + 3, self._nfc_content[4:8])
                data2 = bytes.fromhex('000000007DFDF0793651ABD7466E39C191BABEB856CEEDF1CE44CC75EAFB27094D087AE803003B3C7778860000')
                copyarray(self._bytes, 3 + len(data1) + 3 + 4, data2)
                copyarray(self._bytes, 3 + len(data1) + 3 + 4 + len(data2), self._nfc_content[0:245])
                self.set_action(Action.READ_TAG_2)
            else:
                data = bytes.fromhex('02000927')
                copyarray(self._bytes, 3, data)
                copyarray(self._bytes, 3 + len(data), self._nfc_content[245:])
                self.set_action(Action.READ_FINISHED)
        elif self.get_action() == Action.READ_FINISHED:
            self._bytes[0] = 0x2a
            self._bytes[1] = 0
            self._bytes[2] = 5
            self._bytes[3] = 0
            self._bytes[4] = 0
            data = bytes.fromhex('0931040000000101020007')
            copyarray(self._bytes, 5, data)
            copyarray(self._bytes, 5 + len(data), self._nfc_content[0:3])
            copyarray(self._bytes, 5 + len(data) + 3, self._nfc_content[4:8])

        crc = crc8()
        crc.update(bytes(self._bytes[:-1]))
        self._bytes[-1] = ord(crc.digest())

    def set_nfc(self, nfc_content):
        self._nfc_content = nfc_content

    def __bytes__(self):
        return bytes(self._bytes)
