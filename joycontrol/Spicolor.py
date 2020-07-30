def file_custom_SPI(SpiFile, color):
    if isinstance(color, list):
        print("color is not list")
        return False
    for i in color:
        if i > 255:
            print(i + " is bigger than 255: ERR in Spicolor")
            return False
    r = color[1]
    b = color[2]
    g = color[3]
    r2 = color[4]
    b2 = color[5]
    g2 = color[6]
    Spi = open(SpiFile,"r+b" )
    Spi.seek(0)
    fStart = Spi.read(24656)
    Spi.seek(24662)
    fEnd = Spi.read()
    Spi.close()
    print('\n')
    Spin = open("Spi_color.bin", "w+b")
    Spin.write(fStart + bytes([r]) + bytes([g]) + bytes([b]) + bytes([r2]) + bytes([g2]) + bytes([b2]) + fEnd)
    Spi.close()
    return
def var_custom_SPI(SpiFile, color):
    if isinstance(color, list) != True:
        print("color is not list: ERR in Spicolor")
        return False
    if len(color) < 3:
        print("At least 3 values must be given: ERR in Spicolor")
        return False
    if len(color) < 6:
        color = [color[0], color[1], color[2], color[0], color[1], color[2]]
    for i in color:
        if i > 255:
            print(i + " is bigger than 255: ERR in Spicolor")
            return False
    print(color[0])
    r = color[0]
    b = color[1]
    g = color[2]
    r2 = color[3]
    g2 = color[4]
    b2 = color[5]
    Spi = open(SpiFile, "r+b")
    Spi.seek(0)
    fStart = Spi.read(24656)
    Spi.seek(24662)
    fEnd = Spi.read()
    Spi.close()
    return fStart + bytes([r]) + bytes([g]) + bytes([b]) + bytes([r2]) + bytes([g2]) + bytes([b2]) + fEnd