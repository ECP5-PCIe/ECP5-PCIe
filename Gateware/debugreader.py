import serial, time

ser = serial.Serial(
    port='/dev/ttyUSB1',
    baudrate=1000000,
)

ser.isOpen()

ser.write(b'x')
out = ''
time.sleep(1)
while ser.inWaiting() > 0:
    while ser.inWaiting() > 0:
        out += ser.read(ser.inWaiting()).decode("ascii")
    time.sleep(2)
lines = out.split('\n')[:-1]
for line in lines:
    for part in [line[int(i * 6):int(i * 6 + 6)] for i in range(int(len(line) / 6))]:
        val = 3
        try:
            val = int(part, 16)
        except:
            print("err")
        valid = val & 0x8000 != 0
        k = val & 0x0100 != 0
        x = val & 0b11111
        y = val & 0b11100000 >> 5
        if k and valid:
            print("%d K%d.%d" % (valid, x, y))
        #if k:
        #    print("%d K%d.%d" % (valid, x, y))
        #else:
        #    print("%d D%d.%d" % (valid, x, y))
ser.close()