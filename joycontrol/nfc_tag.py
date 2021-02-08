
import enum
import copy
import asyncio

import logging

logger = logging.getLogger(__name__)

unnamed_saves = 0
default_path = "/tmp/{}.bin"

class NFCTagType(enum.Enum):
    AMIIBO = enum.auto

class NFCTag:
    def __init__(self, length=540, data=None, type=NFCTagType.AMIIBO, source=None, mutable=False, isClone=False):
        self.data: bytes = data if data else bytearray(length)
        self.type = type
        self.mutable = mutable
        self.source = source
        self.isClone = isClone
        if self.type == NFCTagType.AMIIBO and len(self.data) != 540:
            logger.warning("Illegal Amiibo tag size, using zeros")
            self.data = bytearray(540)

    @classmethod
    async def load_amiibo(cls, path):
        # if someone want to make this async have fun
        with open(path, "rb") as reader:
            return NFCTag(data=bytearray(reader.read(540)), type=NFCTagType.AMIIBO, source=path)

    def save(self):
        if not self.source:
            global unnamed_saves
            unnamed_saves += 1
            self.source = default_path.format(unnamed_saves)
            logger.info("Saved amiibo witout source as " + self.source)
        with open(self.source, "wb") as writer:
            writer.write(self.data)

    def getUID(self):
        return self.data[0:3], self.data[4:8]

    def clone(self):
        clone = copy.deepcopy(self)
        if self.isClone:
            clone.source[-1] += 1
        else:
            clone.isClone = True
            clone.source += ".1"
        clone.mutable = True
        return clone

    def write(self, idx, data):
        if not self.mutable:
            logger.warning("Ignored amiibo write to non-mutable amiibo")
        self.data[idx:idx+len(data)] = data

    def __deepcopy__(self, memo):
        return NFCTag(copy.deepcopy(self.data, self.source), memo)
