from gurux_dlms import GXSerial
ser = GXSerial()
ser.open("COM6:300:8Even1")
ser.write(b"/?!\r\n")
print(ser.read(64))  # just read raw bytes
