# Mapa de Hardware Detectado

Este mapa foi extraido do projeto anterior `ula-firmata-python`. O projeto antigo foi usado somente como referencia e nao deve ser alterado.

## Botoes

Os botoes utilizam `INPUT_PULLUP`. Portanto:

- solto: `HIGH`;
- pressionado: `LOW`;
- cada botao deve fechar o circuito entre o pino e o `GND`.

| Funcao | Pino | Evidencia no codigo antigo |
| --- | --- | --- |
| Bit 3 da entrada | D7 | `BUTTON_PINS["b3"] = 7` em `src/ula_app/arduino.py` |
| Bit 2 da entrada | D8 | `BUTTON_PINS["b2"] = 8` em `src/ula_app/arduino.py` |
| Bit 1 da entrada | D9 | `BUTTON_PINS["b1"] = 9` em `src/ula_app/arduino.py` |
| Bit 0 da entrada | D10 | `BUTTON_PINS["b0"] = 10` em `src/ula_app/arduino.py` |
| Confirmar / OK | D11 | `BUTTON_PINS["ok"] = 11` em `src/ula_app/arduino.py` |

O firmware novo aplica debounce de 40 ms e processa somente a transicao para `LOW`.

## LEDs

| Funcao | Pino | Evidencia no codigo antigo |
| --- | --- | --- |
| Carry / borrow | D2 | `LED_PINS["carry"] = 2` e `led_carry = board.get_pin("d:2:o")` |
| Resultado bit 3 | D3 | `LED_PINS["b3"] = 3` |
| Resultado bit 2 | D4 | `LED_PINS["b2"] = 4` |
| Resultado bit 1 | D5 | `LED_PINS["b1"] = 5` |
| Resultado bit 0 | D6 | `LED_PINS["b0"] = 6` |

Cada LED deve usar resistor em serie, tipicamente entre 220 e 330 ohms.

## Potenciometro

| Funcao | Pino | Evidencia no codigo antigo |
| --- | --- | --- |
| Entrada ADC monitorada | A0 | `POTENTIOMETER_PIN = 0` e `board.get_pin("a:0:i")` |

Ligacao esperada:

- uma extremidade em `5V`;
- terminal central em `A0`;
- outra extremidade em `GND`.

O potenciometro e somente monitorado pelo dashboard. Ele nao substitui os botoes nem altera A, B ou a operacao da ULA.

## Operacoes da ULA

| Codigo | Nome | Descricao |
| --- | --- | --- |
| 0 | AND | `A & B` |
| 1 | OR | `A | B` |
| 2 | NOT(B) | Complemento de B limitado a 4 bits |
| 3 | XOR | `A ^ B` |
| 4 | ADD | Soma, resultado nos 4 bits inferiores e carry separado |
| 5 | SUB | Subtracao modular de 4 bits; carry indica borrow |
| 6 | MUL | Multiplicacao; carry e overflow indicam resultado maior que 15 |
| 7 | DIV | Divisao inteira; flag D indica divisao por zero |

## Entradas, saidas e fluxo

1. Os quatro botoes de bits montam o operando A.
2. OK confirma A.
3. Os mesmos botoes montam B.
4. OK confirma B.
5. Os tres bits menos significativos selecionam a operacao.
6. OK executa a ULA e grava uma entrada de historico na EEPROM.
7. O resultado aparece nos LEDs; OK reinicia o fluxo.

Flags da ULA:

- bit 0: `Z`, zero;
- bit 1: `C`, carry/borrow;
- bit 2: `N`, bit mais significativo do resultado;
- bit 3: `V`, overflow da multiplicacao;
- bit 4: `D`, divisao por zero.

## Observacoes

- Todos os pinos necessarios foram encontrados de forma consistente no codigo e na documentacao do projeto antigo.
- Nenhum pino ficou ambiguo; por isso nao ha `TODO AJUSTAR PINO` no sketch atual.
- Os registradores dos timers sao apenas lidos. O firmware nao altera a configuracao do Timer0, Timer1 ou Timer2.
- O Timer0 continua disponivel para `millis()`, `delay()` e funcoes internas do core Arduino.
- A comunicacao nova usa Serial USB propria a 115200 baud e nao depende de Firmata.
