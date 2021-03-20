import enum
from os import path as ph

import logging


logger = logging.getLogger(__name__)

unnamed_saves = 0

def get_savepath(hint='/tmp/amiibo'):
    global unnamed_saves
    unnamed_saves += 1
    if hint.endswith('.bin'):
        hint = hint[:-4]
    while True:
        path = hint + '_' + str(unnamed_saves) + '.bin'
        if not ph.exists(path):
            break
        unnamed_saves += 1
    return path


unnamed_backups = 0

def get_backuppath(hint='/tmp/amiibo.bin'):
    global unnamed_backups
    unnamed_backups += 1
    while True:
        path = hint + '.bak' + str(unnamed_backups)
        if not ph.exists(path):
            break
        unnamed_backups += 1
    return path


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
    def load_amiibo(cls, source):
        # if someone want to make this async have fun
        with open(source, "rb") as reader:
            return NFCTag(data=bytearray(reader.read(540)), tag_type=NFCTagType.AMIIBO, source=source)

    def create_backup(self):
        path = get_backuppath(self.source)
        logger.info("creating amiibo backup at " + path)
        with open(path, "wb") as writer:
            writer.write(self.data)

    def set_mutable(self, mutable=True):
        if mutable > self.mutable:
            self.create_backup()
        self.mutable = mutable

    def save(self):
        if not self.source:
            self.source = get_savepath()
        with open(self.source, "wb") as writer:
            writer.write(self.data)
            logger.info("Saved altered amiibo as " + self.source)

    def getUID(self):
        return self.data[0:3] + self.data[4:8]

    def get_mutable(self):
        if self.mutable:
            return self
        else:
            return NFCTag(self.data.copy(), self.tag_type, True, get_savepath(self.source))

    def write(self, idx, data):
        if not self.mutable:
            logger.warning("Ignored amiibo write to non-mutable amiibo")
        else:
            self.data[idx:idx + len(data)] = data

    def __del__(self):
        self.save()
