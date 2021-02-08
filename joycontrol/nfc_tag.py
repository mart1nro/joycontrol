
import enum

class NFCTagType(enum.Enum):
    AMIIBO = enum.auto

class NFCTag:
    def __init__(self, length=540, data=None, type=NFCTagType.AMIIBO):
        self.data: bytes = data if data else bytearray(length)
        self.type = type
        if self.type == NFCTagType.AMIIBO and len(self.data) != 540:
            self.data = bytearray(540)

    def getUID(self):
        return self.data[0:3], self.data[4:8]

    def write(self, idx, data):
        self.data[idx:idx+len(data)] = data
