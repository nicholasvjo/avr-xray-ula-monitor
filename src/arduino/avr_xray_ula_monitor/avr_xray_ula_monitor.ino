#include <Arduino.h>
#include <EEPROM.h>
#include <avr/io.h>
#include <avr/pgmspace.h>

// Hardware map recovered from the previous Firmata project.
const uint8_t LED_CARRY_PIN = 2;
const uint8_t LED_BIT_PINS[4] = {3, 4, 5, 6};  // b3, b2, b1, b0
const uint8_t BUTTON_BIT_PINS[4] = {7, 8, 9, 10};  // b3, b2, b1, b0
const uint8_t BUTTON_OK_PIN = 11;
const uint8_t POTENTIOMETER_PIN = A0;

const unsigned long SNAPSHOT_INTERVAL_MS = 100;
const unsigned long DEBOUNCE_MS = 40;
const uint8_t PROTOCOL_VERSION = 1;

const uint8_t FLAG_ZERO = 1 << 0;
const uint8_t FLAG_CARRY = 1 << 1;
const uint8_t FLAG_NEGATIVE = 1 << 2;
const uint8_t FLAG_OVERFLOW = 1 << 3;
const uint8_t FLAG_DIV_ZERO = 1 << 4;

const uint8_t EEPROM_MAGIC = 0xA5;
const uint8_t EEPROM_RECORD_SIZE = 5;
const uint8_t EEPROM_RECORD_COUNT = 32;
const uint16_t EEPROM_DUMP_SIZE = 192;
const uint8_t FLASH_DUMP_SIZE = 64;

enum InputStage : uint8_t {
  STAGE_INPUT_A = 0,
  STAGE_INPUT_B = 1,
  STAGE_INPUT_OPERATION = 2,
  STAGE_RESULT = 3
};

struct DebouncedButton {
  uint8_t pin;
  uint8_t stableState;
  uint8_t lastRawState;
  unsigned long changedAt;
};

volatile uint8_t ula_probe[128];

DebouncedButton bitButtons[4];
DebouncedButton okButton;

uint8_t operandA = 0;
uint8_t operandB = 0;
uint8_t operationCode = 0;
uint8_t resultValue = 0;
uint8_t ulaFlags = 0;
uint8_t currentInput = 0;
InputStage inputStage = STAGE_INPUT_A;

uint8_t probeHistoryIndex = 0;
uint8_t operationSequence = 0;
uint32_t snapshotSequence = 0;
unsigned long lastSnapshotAt = 0;

char commandBuffer[24];
uint8_t commandLength = 0;

void setupButton(DebouncedButton &button, uint8_t pin);
void processButton(DebouncedButton &button, void (*onPress)());
void processButtons();
void pressBit3();
void pressBit2();
void pressBit1();
void pressBit0();
void pressOk();
void toggleInputBit(uint8_t bit);
void executeUla();
void writeLeds(uint8_t value, bool carry);
void updateProbe(uint16_t adcValue);
void appendProbeHistory();
void persistOperation();
void processSerialCommands();
void handleCommand();
void sendHello();
void sendSnapshot(uint16_t adcValue);
void sendStaticMemory();
void printHexByte(uint8_t value);
void printProbeHex();
void printEepromHex();
void printFlashHex();

void setup() {
  Serial.begin(115200);

  pinMode(LED_CARRY_PIN, OUTPUT);
  for (uint8_t index = 0; index < 4; index++) {
    pinMode(LED_BIT_PINS[index], OUTPUT);
  }

  for (uint8_t index = 0; index < 4; index++) {
    setupButton(bitButtons[index], BUTTON_BIT_PINS[index]);
  }
  setupButton(okButton, BUTTON_OK_PIN);

  for (uint8_t index = 0; index < sizeof(ula_probe); index++) {
    ula_probe[index] = 0;
  }

  writeLeds(0, false);
  sendHello();
}

void loop() {
  processSerialCommands();
  processButtons();

  const uint16_t adcValue = analogRead(POTENTIOMETER_PIN);
  updateProbe(adcValue);

  const unsigned long now = millis();
  if (now - lastSnapshotAt >= SNAPSHOT_INTERVAL_MS) {
    lastSnapshotAt = now;
    sendSnapshot(adcValue);
  }
}

void setupButton(DebouncedButton &button, uint8_t pin) {
  pinMode(pin, INPUT_PULLUP);
  const uint8_t initialState = digitalRead(pin);
  button.pin = pin;
  button.stableState = initialState;
  button.lastRawState = initialState;
  button.changedAt = millis();
}

void processButton(DebouncedButton &button, void (*onPress)()) {
  const uint8_t rawState = digitalRead(button.pin);
  const unsigned long now = millis();

  if (rawState != button.lastRawState) {
    button.lastRawState = rawState;
    button.changedAt = now;
  }

  if (
    rawState != button.stableState &&
    now - button.changedAt >= DEBOUNCE_MS
  ) {
    button.stableState = rawState;

    // INPUT_PULLUP: a pressed button is electrically LOW.
    if (button.stableState == LOW) {
      onPress();
    }
  }
}

void processButtons() {
  processButton(bitButtons[0], pressBit3);
  processButton(bitButtons[1], pressBit2);
  processButton(bitButtons[2], pressBit1);
  processButton(bitButtons[3], pressBit0);
  processButton(okButton, pressOk);
}

void pressBit3() {
  toggleInputBit(3);
}

void pressBit2() {
  toggleInputBit(2);
}

void pressBit1() {
  toggleInputBit(1);
}

void pressBit0() {
  toggleInputBit(0);
}

void toggleInputBit(uint8_t bit) {
  if (inputStage == STAGE_RESULT) {
    return;
  }

  currentInput ^= (1 << bit);
  writeLeds(currentInput, false);
}

void pressOk() {
  if (inputStage == STAGE_INPUT_A) {
    operandA = currentInput & 0x0F;
    currentInput = 0;
    inputStage = STAGE_INPUT_B;
    writeLeds(0, false);
    return;
  }

  if (inputStage == STAGE_INPUT_B) {
    operandB = currentInput & 0x0F;
    currentInput = 0;
    inputStage = STAGE_INPUT_OPERATION;
    writeLeds(0, false);
    return;
  }

  if (inputStage == STAGE_INPUT_OPERATION) {
    operationCode = currentInput & 0x07;
    currentInput = 0;
    executeUla();
    inputStage = STAGE_RESULT;
    writeLeds(resultValue, (ulaFlags & FLAG_CARRY) != 0);

    // EEPROM writes only happen here, after the operation is confirmed.
    persistOperation();
    appendProbeHistory();
    return;
  }

  inputStage = STAGE_INPUT_A;
  currentInput = 0;
  writeLeds(0, false);
}

void executeUla() {
  ulaFlags = 0;
  resultValue = 0;

  switch (operationCode) {
    case 0:
      resultValue = operandA & operandB;
      break;

    case 1:
      resultValue = operandA | operandB;
      break;

    case 2:
      resultValue = (~operandB) & 0x0F;
      break;

    case 3:
      resultValue = operandA ^ operandB;
      break;

    case 4: {
      const uint8_t total = operandA + operandB;
      if (total > 15) {
        ulaFlags |= FLAG_CARRY;
      }
      resultValue = total & 0x0F;
      break;
    }

    case 5:
      if (operandA < operandB) {
        ulaFlags |= FLAG_CARRY;
      }
      resultValue = (operandA - operandB) & 0x0F;
      break;

    case 6: {
      const uint16_t product = operandA * operandB;
      if (product > 15) {
        ulaFlags |= FLAG_CARRY;
        ulaFlags |= FLAG_OVERFLOW;
      }
      resultValue = product & 0x0F;
      break;
    }

    case 7:
      if (operandB == 0) {
        ulaFlags |= FLAG_DIV_ZERO;
        resultValue = 0;
      } else {
        resultValue = operandA / operandB;
      }
      break;
  }

  if (resultValue == 0) {
    ulaFlags |= FLAG_ZERO;
  }
  if (resultValue & 0x08) {
    ulaFlags |= FLAG_NEGATIVE;
  }
}

void writeLeds(uint8_t value, bool carry) {
  digitalWrite(LED_CARRY_PIN, carry ? HIGH : LOW);
  digitalWrite(LED_BIT_PINS[0], (value >> 3) & 1);
  digitalWrite(LED_BIT_PINS[1], (value >> 2) & 1);
  digitalWrite(LED_BIT_PINS[2], (value >> 1) & 1);
  digitalWrite(LED_BIT_PINS[3], value & 1);
}

void updateProbe(uint16_t adcValue) {
  ula_probe[0] = operandA;
  ula_probe[1] = operandB;
  ula_probe[2] = operationCode;
  ula_probe[3] = resultValue;
  ula_probe[4] = ulaFlags;
  ula_probe[5] = SREG;
  ula_probe[6] = PORTB;
  ula_probe[7] = PORTC;
  ula_probe[8] = PORTD;
  ula_probe[9] = PINB;
  ula_probe[10] = PINC;
  ula_probe[11] = PIND;
  ula_probe[12] = TCNT0;
  ula_probe[13] = TCNT2;
  ula_probe[14] = adcValue & 0xFF;
  ula_probe[15] = (adcValue >> 8) & 0xFF;
}

void appendProbeHistory() {
  const uint8_t base = 16 + probeHistoryIndex * 7;
  ula_probe[base + 0] = operandA;
  ula_probe[base + 1] = operandB;
  ula_probe[base + 2] = operationCode;
  ula_probe[base + 3] = resultValue;
  ula_probe[base + 4] = ulaFlags;
  ula_probe[base + 5] = SREG;
  ula_probe[base + 6] = operationSequence++;
  probeHistoryIndex = (probeHistoryIndex + 1) % 16;
}

void persistOperation() {
  uint8_t writeIndex = EEPROM.read(1);
  uint8_t count = EEPROM.read(2);
  const bool validHeader = (
    EEPROM.read(0) == EEPROM_MAGIC &&
    EEPROM.read(3) == EEPROM_RECORD_SIZE &&
    writeIndex < EEPROM_RECORD_COUNT &&
    count <= EEPROM_RECORD_COUNT
  );

  if (!validHeader) {
    writeIndex = 0;
    count = 0;
    EEPROM.update(0, EEPROM_MAGIC);
    EEPROM.update(1, writeIndex);
    EEPROM.update(2, count);
    EEPROM.update(3, EEPROM_RECORD_SIZE);
  }

  const uint16_t base = 4 + writeIndex * EEPROM_RECORD_SIZE;
  EEPROM.update(base + 0, operandA);
  EEPROM.update(base + 1, operandB);
  EEPROM.update(base + 2, operationCode);
  EEPROM.update(base + 3, resultValue);
  EEPROM.update(base + 4, ulaFlags);

  writeIndex = (writeIndex + 1) % EEPROM_RECORD_COUNT;
  if (count < EEPROM_RECORD_COUNT) {
    count++;
  }
  EEPROM.update(1, writeIndex);
  EEPROM.update(2, count);
}

void processSerialCommands() {
  while (Serial.available() > 0) {
    const char character = Serial.read();

    if (character == '\n' || character == '\r') {
      if (commandLength > 0) {
        commandBuffer[commandLength] = '\0';
        handleCommand();
        commandLength = 0;
      }
      continue;
    }

    if (commandLength < sizeof(commandBuffer) - 1) {
      commandBuffer[commandLength++] = character;
    } else {
      commandLength = 0;
    }
  }
}

void handleCommand() {
  if (strcmp(commandBuffer, "GET_STATIC") == 0) {
    sendStaticMemory();
  }
}

void sendHello() {
  Serial.print(F("{\"type\":\"hello\",\"protocol\":"));
  Serial.print(PROTOCOL_VERSION);
  Serial.print(F(",\"device\":\"AVR X-Ray ATmega328P\",\"firmware\":\"1.0.0\",\"sample_hz\":10}"));
  Serial.println();
}

void sendSnapshot(uint16_t adcValue) {
  const uint8_t sregValue = SREG;
  const uint8_t interruptState = SREG;
  cli();
  const uint16_t timer1Value = TCNT1;
  SREG = interruptState;
  const uint16_t millivolts = (uint32_t)adcValue * 5000UL / 1023UL;

  Serial.print(F("{\"type\":\"snapshot\",\"protocol\":"));
  Serial.print(PROTOCOL_VERSION);
  Serial.print(F(",\"seq\":"));
  Serial.print(snapshotSequence++);
  Serial.print(F(",\"millis\":"));
  Serial.print(millis());

  Serial.print(F(",\"ula\":{\"a\":"));
  Serial.print(operandA);
  Serial.print(F(",\"b\":"));
  Serial.print(operandB);
  Serial.print(F(",\"op\":"));
  Serial.print(operationCode);
  Serial.print(F(",\"result\":"));
  Serial.print(resultValue);
  Serial.print(F(",\"flags\":"));
  Serial.print(ulaFlags);
  Serial.print(F(",\"stage\":"));
  Serial.print((uint8_t)inputStage);
  Serial.print(F(",\"input\":"));
  Serial.print(currentInput);
  Serial.print('}');

  Serial.print(F(",\"ports\":{\"B\":{\"ddr\":"));
  Serial.print(DDRB);
  Serial.print(F(",\"port\":"));
  Serial.print(PORTB);
  Serial.print(F(",\"pin\":"));
  Serial.print(PINB);
  Serial.print(F("},\"C\":{\"ddr\":"));
  Serial.print(DDRC);
  Serial.print(F(",\"port\":"));
  Serial.print(PORTC);
  Serial.print(F(",\"pin\":"));
  Serial.print(PINC);
  Serial.print(F("},\"D\":{\"ddr\":"));
  Serial.print(DDRD);
  Serial.print(F(",\"port\":"));
  Serial.print(PORTD);
  Serial.print(F(",\"pin\":"));
  Serial.print(PIND);
  Serial.print(F("}}"));

  Serial.print(F(",\"sreg\":"));
  Serial.print(sregValue);

  Serial.print(F(",\"timers\":{\"tcnt0\":"));
  Serial.print(TCNT0);
  Serial.print(F(",\"tcnt1\":"));
  Serial.print(timer1Value);
  Serial.print(F(",\"tcnt2\":"));
  Serial.print(TCNT2);
  Serial.print(F(",\"tccr0a\":"));
  Serial.print(TCCR0A);
  Serial.print(F(",\"tccr0b\":"));
  Serial.print(TCCR0B);
  Serial.print(F(",\"tccr1a\":"));
  Serial.print(TCCR1A);
  Serial.print(F(",\"tccr1b\":"));
  Serial.print(TCCR1B);
  Serial.print(F(",\"tccr2a\":"));
  Serial.print(TCCR2A);
  Serial.print(F(",\"tccr2b\":"));
  Serial.print(TCCR2B);
  Serial.print('}');

  Serial.print(F(",\"adc\":{\"a0\":"));
  Serial.print(adcValue);
  Serial.print(F(",\"millivolts\":"));
  Serial.print(millivolts);
  Serial.print('}');

  Serial.print(F(",\"sram\":\""));
  printProbeHex();
  Serial.print(F("\"}"));
  Serial.println();
}

void sendStaticMemory() {
  Serial.print(F("{\"type\":\"memory\",\"protocol\":"));
  Serial.print(PROTOCOL_VERSION);
  Serial.print(F(",\"eeprom\":\""));
  printEepromHex();
  Serial.print(F("\",\"flash\":\""));
  printFlashHex();
  Serial.print(F("\"}"));
  Serial.println();
}

void printHexByte(uint8_t value) {
  const char hexDigits[] = "0123456789ABCDEF";
  Serial.print(hexDigits[(value >> 4) & 0x0F]);
  Serial.print(hexDigits[value & 0x0F]);
}

void printProbeHex() {
  for (uint8_t index = 0; index < sizeof(ula_probe); index++) {
    printHexByte(ula_probe[index]);
  }
}

void printEepromHex() {
  for (uint16_t index = 0; index < EEPROM_DUMP_SIZE; index++) {
    printHexByte(EEPROM.read(index));
  }
}

void printFlashHex() {
  for (uint8_t index = 0; index < FLASH_DUMP_SIZE; index++) {
    printHexByte(pgm_read_byte_near(index));
  }
}
