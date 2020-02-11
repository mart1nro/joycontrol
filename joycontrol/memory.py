
class FlashMemory:
    def __init__(self, spi_flash_memory_data=None, size=0x80000):
        if spi_flash_memory_data is None:
            self.data = size * [0x00]
        else:
            if len(spi_flash_memory_data) != size:
                raise ValueError(f'Given data size {len(spi_flash_memory_data)} does not match size {size}.')
            if isinstance(spi_flash_memory_data, bytes):
                spi_flash_memory_data = list(spi_flash_memory_data)
            self.data = spi_flash_memory_data

    def __getitem__(self, item):
        return self.data[item]

    def get_factory_l_stick_calibration(self):
        """
        :returns 9 left stick factory calibration bytes
        """
        return self.data[0x603D:0x6046]

    def get_factory_r_stick_calibration(self):
        """
        :returns 9 right stick factory calibration bytes
        """
        return self.data[0x6046:0x604F]

    def get_user_l_stick_calibration(self):
        """
        :returns 9 left stick user calibration bytes if the data is available, otherwise None
        """
        # check if calibration data is available:
        if self.data[0x8010] == 0xB2 and self.data[0x8011] == 0xA1:
            return self.data[0x8012:0x801B]
        else:
            return None

    def get_user_r_stick_calibration(self):
        """
        :returns 9 right stick user calibration bytes if the data is available, otherwise None
        """
        # check if calibration data is available:
        if self.data[0x801B] == 0xB2 and self.data[0x801C] == 0xA1:
            return self.data[0x801D:0x8026]
        else:
            return None
