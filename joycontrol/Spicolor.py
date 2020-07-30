def file_custom_SPI(SpiFile, color):
    color = color.split()
    if len(color) < 3:
        print("At least 3 values must be given: ERR in Spicolor")
        return False
    if len(color) < 6:
        color = [color[0], color[1], color[2], color[0], color[1], color[2]]
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
    color = color.split()
    if len(color) < 3:
        print("At least 3 values must be given: ERR in Spicolor")
        return False
    if len(color) < 6:
        color = [color[0], color[1], color[2], color[0], color[1], color[2]]
    for i in color:
        try:
            i = int(i)
        except:
            print(i + "is not convertable to int")
        if i > 255:
            print(i + " is bigger than 255: ERR in Spicolor")
            return False
    r = int(color[0])
    b = int(color[1])
    g = int(color[2])
    r2 = int(color[3])
    g2 = int(color[4])
    b2 = int(color[5])
    Spi = open(SpiFile, "r+b")
    Spi.seek(0)
    fStart = Spi.read(24656)
    Spi.seek(24662)
    fEnd = Spi.read()
    Spi.close()
    return fStart + bytes([r]) + bytes([g]) + bytes([b]) + bytes([r2]) + bytes([g2]) + bytes([b2]) + fEnd
