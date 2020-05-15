void setup()
{
  Serial.begin(115200);
}

void loop()
{
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