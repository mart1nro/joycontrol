def file_custom_SPI(SpiFile, r, g, b, r2, g2, b2):
    color = [r, g, b, r2, g2, b2]
    for i in color:
        if i > 255:
            print(i + " is bigger than 255")
            quit()
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
def var_custom_SPI(SpiFile, r, g, b, r2, g2, b2):
    color = [r, g, b, r2, g2, b2]
    for i in color:
        if i > 255:
            print(i + " is bigger than 255")
            quit()
    Spi = open(SpiFile, "r+b")
    Spi.seek(0)
    fStart = Spi.read(24656)
    Spi.seek(24662)
    fEnd = Spi.read()
    Spi.close()
    return fStart + bytes([r]) + bytes([g]) + bytes([b]) + bytes([r2]) + bytes([g2]) + bytes([b2]) + fEnd