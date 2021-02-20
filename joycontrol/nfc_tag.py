import enum
from os import path as ph

import logging

logger = logging.getLogger(__name__)

unnamed_saves = 0
hint_path = "/tmp/{}_{}.bin"
default_path = "/tmp/{}.bin"


def get_savepath(hint=None):
    global unnamed_saves, default_path
    unnamed_saves += 1
    return hint_path.format(hint, unnamed_saves) if hint else default_path.format(unnamed_saves)


class NFCTagType(enum.Enum):
    AMIIBO = enum.auto


class NFCTag:
    def __init__(self, data, tag_type: NFCTagType = NFCTagType.AMIIBO, mutable=False, source=None):
        self.data: bytearray = bytearray(data)
        self.tag_type: NFCTagType = tag_type
        self.mutable: bool = mutable
        self.source: str = source
        if self.tag_type == NFCTagType.AMIIBO and len(self.data) != 540:
            logger.warning("Illegal Amiibo tag size")

    @classmethod
    def load_amiibo(cls, path):
        # if someone want to make this async have fun
        with open(path, "rb") as reader:
            return NFCTag(data=bytearray(reader.read(540)), tag_type=NFCTagType.AMIIBO, source=path)

    def save(self):
        if self.mutable:
            if not self.source:
                self.source = get_savepath()
                logger.info("Saved amiibo without source as " + self.source)
            with open(self.source, "wb") as writer:
                writer.write(self.data)

    def getUID(self):
        return self.data[0:3] + self.data[4:8]

    def get_mutable(self):
        if self.mutable:
            return self
        else:
            return NFCTag(self.data.copy(), self.tag_type, True, get_savepath(ph.splitext(ph.basename(self.source))[0]))

    def write(self, idx, data):
        if not self.mutable:
            logger.warning("Ignored amiibo write to non-mutable amiibo")
        self.data[idx:idx + len(data)] = data

    def __del__(self):
        self.save()
