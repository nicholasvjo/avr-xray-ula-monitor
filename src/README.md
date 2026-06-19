# AVR X-Ray - ATmega328P Internal Monitor

## English

### Overview

AVR X-Ray is a desktop dashboard for inspecting an Arduino Uno and its ATmega328P while a physical 4-bit ALU workflow runs on the board.

The project uses:

- a dedicated Arduino C/C++ sketch;
- a custom USB Serial protocol at `115200` baud;
- Python with `pyserial`;
- a required CustomTkinter graphical interface;
- a terminal dashboard;
- a complete simulator that does not require hardware.

Firmata is not used by the final project. The previous Firmata project was inspected only to recover the hardware mapping and the 4-bit ALU behavior.

### Project location

Run every Python command from the new project source directory:

```bash
cd arduino-memory-dump/src
```

The launcher is `main.py`.

### Hardware mapping

| Function | Arduino Uno pin |
| --- | --- |
| Carry LED | D2 |
| Result LEDs b3, b2, b1, b0 | D3, D4, D5, D6 |
| Input buttons b3, b2, b1, b0 | D7, D8, D9, D10 |
| Confirm / OK button | D11 |
| Monitored potentiometer | A0 |

LEDs require series resistors, typically 220 to 330 ohms.

Buttons use `INPUT_PULLUP`. Connect one side of each button to its digital pin and the other side to `GND`. Released is `HIGH`; pressed is `LOW`. The sketch includes 40 ms debounce and counts only the press transition.

Connect the potentiometer ends to `5V` and `GND`, and its middle terminal to `A0`. It is only monitored by the ADC dashboard and does not replace the ALU buttons.

See [docs/hardware_map.md](docs/hardware_map.md) for the evidence recovered from the old project.

### ALU workflow

The same four bit buttons are reused across these stages:

1. Build operand A and press OK.
2. Build operand B and press OK.
3. Build the operation code and press OK.
4. Read the result on the LEDs and dashboard.
5. Press OK to start again.

| Code | Operation |
| --- | --- |
| 0 | AND |
| 1 | OR |
| 2 | NOT(B), limited to 4 bits |
| 3 | XOR |
| 4 | Addition |
| 5 | Subtraction with borrow |
| 6 | Multiplication with overflow |
| 7 | Integer division with division-by-zero detection |

ULA flags are `Z` (zero), `C` (carry/borrow), `N` (result bit 3), `V` (multiplication overflow), and `D` (division by zero).

### Uploading the Arduino sketch

Open this file in the Arduino IDE:

```text
arduino/avr_xray_ula_monitor/avr_xray_ula_monitor.ino
```

Select:

- Board: `Arduino Uno`
- Port: the port assigned to the board

Then click Upload. Close the Arduino Serial Monitor before starting Python.

Arduino CLI alternative:

```bash
arduino-cli compile --fqbn arduino:avr:uno arduino/avr_xray_ula_monitor
arduino-cli upload --fqbn arduino:avr:uno --port COM3 arduino/avr_xray_ula_monitor
```

On Linux, replace `COM3` with a device such as `/dev/ttyACM0`.

### Python installation

Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r python\requirements.txt
```

Linux:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r python/requirements.txt
```

The project depends only on `customtkinter` and `pyserial`. It does not install `pyFirmata2`.

### Running

GUI with automatic port selection:

```bash
python main.py
```

GUI with an explicit port:

```bash
python main.py --port COM3
python main.py --port /dev/ttyACM0
```

Custom baud rate:

```bash
python main.py --baud 115200
```

GUI simulator:

```bash
python main.py --simulate
```

Terminal mode:

```bash
python main.py --terminal --port COM3
python main.py --terminal --simulate
```

### Dashboard

The GUI contains four working views:

- **Visao Geral:** ALU state, operation reference, flag legend, SREG, ADC A0, and the recent EEPROM operation table.
- **Portas:** DDRB/C/D, PORTB/C/D and PINB/C/D with bit-level displays.
- **Timers:** TCNT0/1/2 and TCCR0/1/2 A/B.
- **Memoria:** enlarged live SRAM heatmap, detailed address inspector, EEPROM dump, and FLASH dump.

Timer registers are read only. The sketch does not reconfigure Timer0, Timer1, or Timer2. This is especially important because the Arduino core uses Timer0 for `millis()`, `delay()`, and internal timing.

### SRAM heatmap

The sketch owns a real region:

```cpp
volatile uint8_t ula_probe[128];
```

The heatmap is a `16 x 8` grid. Every cell is one byte:

- brighter cells have larger values;
- changed bytes receive a temporary amber outline;
- clicking a cell shows its index, decimal, hexadecimal, binary, and known meaning.

The ATmega328P has 2,048 bytes of SRAM. The instrumented `ula_probe`
window shows 128 bytes, or 6.25% of the total SRAM.

Offsets `0..15` contain current ALU, CPU, port, timer, and ADC data. Offsets `16..127` contain a 16-entry circular ALU history.

### EEPROM, FLASH, and GET_STATIC

EEPROM stores up to 32 confirmed ALU operations. It is written only after the operation-selection stage is confirmed with OK. `EEPROM.update()` avoids unnecessary writes.

FLASH is read with `pgm_read_byte_near()` and normally remains unchanged while the program runs.

The Python client sends:

```text
GET_STATIC
```

after connecting and whenever the user presses the `GET_STATIC` button. The Arduino then resends the EEPROM and FLASH dumps.

### Serial protocol

The sketch generates compact JSON Lines manually with `Serial.print()`. ArduinoJson is deliberately avoided to reduce SRAM usage.

Message types:

- `hello`: protocol and firmware identification;
- `snapshot`: live ALU, registers, timers, ADC, and SRAM;
- `memory`: EEPROM and FLASH dumps.

The protocol version is `1`, and live snapshots are sent at approximately 10 Hz.

### Tests

From `arduino-memory-dump/src`:

```bash
python -m unittest discover -s tests
```

The tests cover protocol validation and round trips, simulator output, serial-port selection, EEPROM history decoding, and all 2,048 combinations of 4-bit inputs and operations.

### Limitations

- The monitor exposes selected ATmega328P registers, not every peripheral register.
- Serial snapshots slightly affect execution timing.
- FLASH is a small diagnostic window, not a full program-memory dump.
- EEPROM history has 32 circular records.
- The GUI cannot prove electrical wiring; use the hardware map and verify common ground.
- The project targets the Arduino Uno / ATmega328P register layout.

## Portugues

### Visao geral

O AVR X-Ray e um dashboard para observar internamente o ATmega328P de um Arduino Uno enquanto uma ULA fisica de 4 bits e operada pelos botoes.

O projeto usa sketch C/C++ proprio, Serial USB a `115200`, Python com `pyserial`, interface CustomTkinter, modo terminal e simulador completo. A versao final nao usa Firmata.

### Execucao

Todos os comandos devem partir desta pasta:

```bash
cd arduino-memory-dump/src
```

Instalacao no Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r python\requirements.txt
```

Instalacao no Linux:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r python/requirements.txt
```

Comandos principais:

```bash
python main.py
python main.py --port COM3
python main.py --port /dev/ttyACM0
python main.py --simulate
python main.py --terminal --port COM3
python main.py --terminal --simulate
```

### Arduino

Grave no Arduino Uno:

```text
arduino/avr_xray_ula_monitor/avr_xray_ula_monitor.ino
```

Feche o Serial Monitor antes de abrir o Python. Os botoes usam `INPUT_PULLUP`, portanto pressionado e `LOW`. O firmware aplica debounce de 40 ms.

Mapeamento:

- D2: LED carry;
- D3-D6: LEDs b3-b0;
- D7-D10: botoes b3-b0;
- D11: botao OK;
- A0: potenciometro somente para monitoramento ADC.

O arquivo [docs/hardware_map.md](docs/hardware_map.md) documenta as evidencias do projeto antigo.

### Funcionamento

O fluxo da ULA e `A -> B -> operacao -> resultado`. A EEPROM recebe um registro somente quando a operacao e confirmada com OK.

O painel mostra:

- ULA e flags `Z`, `C`, `N`, `V`, `D`;
- tabela de referencia das operacoes e legenda das flags;
- historico recente da EEPROM em formato tabular na Visao Geral;
- DDR, PORT e PIN dos grupos B, C e D;
- SREG;
- TCNT0/1/2 e TCCR0/1/2 A/B;
- ADC A0 e tensao aproximada;
- mapa de calor ampliado de `ula_probe[128]`;
- inspetor detalhado dos enderecos monitorados;
- dump da EEPROM;
- janela de FLASH.

O firmware apenas le os registradores dos timers. Ele nao altera suas configuracoes.

### Protocolo e memorias

O Arduino gera JSON Lines manualmente com `Serial.print()`, sem ArduinoJson. Snapshots sao enviados a aproximadamente 10 Hz.

O comando `GET_STATIC` reenvia EEPROM e FLASH. O Python envia esse comando ao conectar e pelo botao da interface.

O ATmega328P possui 2.048 bytes de SRAM. O mapa de calor representa uma
janela instrumentada de 128 bytes, equivalente a 6,25% da SRAM total, em uma
grade `16 x 8`. Bytes alterados sao destacados, e o clique mostra valor,
significado e uma explicacao didatica do endereco.

### Testes

```bash
python -m unittest discover -s tests
```

O modo `python main.py --simulate` e a forma recomendada de validar manualmente a interface sem o Arduino.
