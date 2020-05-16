#include <Arduino.h>
#include <SPI.h>

const int chipSelectPin = 10;

void writeRegister(byte reg, byte val)
{
  digitalWrite(chipSelectPin, LOW);

  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3)); // See Page 91 of si53xx-reference-manual.pdf
  SPI.transfer(0);
  SPI.transfer(reg);
  SPI.endTransaction();
  
  digitalWrite(chipSelectPin, HIGH);
  digitalWrite(chipSelectPin, LOW);

  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  SPI.transfer(0b01000000);
  SPI.transfer(val);
  SPI.endTransaction();

  digitalWrite(chipSelectPin, HIGH);
}

byte readRegister(byte reg)
{
  digitalWrite(chipSelectPin, LOW);

  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3)); // See Page 91 of si53xx-reference-manual.pdf
  SPI.transfer(0);
  SPI.transfer(reg);
  SPI.endTransaction();

  digitalWrite(chipSelectPin, HIGH);
  digitalWrite(chipSelectPin, LOW);

  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  SPI.transfer(0b10000000);
  byte rval = SPI.transfer(0);
  SPI.endTransaction();

  digitalWrite(chipSelectPin, HIGH);

  return rval;
}

void testSequence()
{
  writeRegister(136, 0b10000000); // Reset
  delay(100);
  writeRegister(4, 0b10010010); // Autosel revertive
  writeRegister(6, 0b00001111); // LVDS to ECP5, disable to SERDES
  writeRegister(41, 1); // Set N2 such that at Fin = 16 MHz that Fpll = 4992 MHz
  writeRegister(42, 56);
  writeRegister(45, 0); // Divide in0 by 1
  writeRegister(48, 1); // Divide in1 by 2
  writeRegister(33, 21); // 60 MHz out1
  writeRegister(36, 101); // 10 MHz out2
  writeRegister(136, 0b01000000); // Calibrate
}

void setup()
{
  SPI.begin();
  Serial.begin(115200);
  pinMode(5, OUTPUT);
  digitalWrite(5, LOW);
  testSequence();
}

void loop()
{
  Serial.println(readRegister(135));
  if (Serial.available() > 0)
  {
    char symbol = Serial.read();
    switch (symbol)
    {
    case 0x30:
      while (Serial.available() == 0)
        ;
      if (Serial.read() == 0x20)
      {
        goto * 0x7000;
      }
      break;
    default:
      Serial.write(symbol);
      break;
    }
  }
}