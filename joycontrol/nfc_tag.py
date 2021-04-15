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
    """
    Class that represents a (Amiibo) NFC-Tag usually backed by a file. If needed files are generated.
    """
    def __init__(self, data, tag_type: NFCTagType = NFCTagType.AMIIBO, mutable=False, source=None):
        self.data: bytearray = bytearray(data)
        self.tag_type: NFCTagType = tag_type
        self.mutable: bool = mutable
        self.source: str = source
        if self.tag_type == NFCTagType.AMIIBO:
            if len(self.data) == 540:
                pass
            elif len(self.data) == 572:
                logger.info("Long amiibo loaded, manufacturer signature is ignored")
            else:
                logger.warning("Illegal Amiibo tag size")

    @classmethod
    def load_amiibo(cls, source):
        # if someone want to make this async have fun
        with open(source, "rb") as reader:
            return NFCTag(data=bytearray(reader.read()), tag_type=NFCTagType.AMIIBO, source=source)

    def create_backup(self):
        """
        copy the file backing this Tag
        """
        path = get_backuppath(self.source)
        logger.info(f"creating amiibo backup at {path}")
        with open(path, "wb") as writer:
            writer.write(self.data)

    def set_mutable(self, mutable=True):
        """
        By default tags are marked immutable to prevent corruption. To make them mutable create a backup first.
        @param mutable:
        @return:
        """
        if mutable > self.mutable:
            self.create_backup()
        self.mutable = mutable

    def save(self):
        if not self.source:
            self.source = get_savepath()
        with open(self.source, "wb") as writer:
            writer.write(self.data)
            logger.info(f"Saved altered amiibo as {self.source}")

    def getUID(self):
        return self.data[0:3] + self.data[4:8]

    def is_mutable(self):
        return self.mutable

    def write(self, idx, data):
        if idx > len(self.data) or idx+len(data) > len(self.data):
            logger.error(f"I Fucking hate pyhton {idx}, {bytes(data).hex()} {len(data)}")
        if not self.mutable:
            logger.warning("Ignored amiibo write to non-mutable amiibo")
        else:

            self.data[idx:idx + len(data)] = data

