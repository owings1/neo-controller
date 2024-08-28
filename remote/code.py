from __future__ import annotations

from defaults import *

try:
  from settings import *
except ImportError as e:
  print(f'Error loading settings: {type(e).__name__}: {e}')

from terms import *

try:
  from typing import Any
except ImportError:
  pass

import board
import busio
import keypad
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms
from digitalio import DigitalInOut, Direction
from microcontroller import Pin

OFF, ON = OFFON = True, False

serial: busio.UART|None = None
actled: DigitalInOut|None = None
ctlled: DigitalInOut|None = None
keys: keypad.Keys|None = None
layout = (
  ('color', 'control'),
  ('pixel', 'control'),
  ('brightness', 'control'),
  ('clear', 'change'),
  ('minus', 'change'),
  ('plus', 'change'),
  ('f1', 'control'),
  ('f2', 'control'),
  ('f3', 'control'),
)
fmap = {
  'f1': {
    'clear': 'restore',
    'minus': 'draw',
    'plus': 'save',
  },
  'f2': {
    'clear': '',
    'minus': '',
    'plus': '',
  },
  'f3': {
    'clear': '',
    'minus': '',
    'plus': '',
  }
}
control: dict[str, bool] = {}
selected: dict[str, Any] = {}
offat: dict[DigitalInOut, int] = {}
colors = ('white', 'red', 'green', 'blue')

def main() -> None:
  try:
    init()
    while True:
      loop()
  finally:
    deinit()

def init() -> None:
  global actled, ctlled, keys, serial
  serial = busio.UART(
    board.TX,
    board.RX,
    baudrate=baudrate,
    timeout=0.1)
  for label, keytype in layout:
    if keytype == 'control':
      control[label] = False
  keys = keypad.Keys(
    tuple(getattr(board, pin) for pin in button_pins),
    value_when_pressed=False,
    pull=True)
  actled = init_led(board.LED_GREEN)
  ctlled = init_led(board.LED_BLUE)
  selected['color'] = 0

def deinit() -> None:
  if serial:
    serial.deinit()
  if keys:
    keys.deinit()
  if actled:
    actled.deinit()
  if ctlled:
    ctlled.deinit()
  offat.clear()
  control.clear()

def loop() -> None:
  event = keys.events.get()
  if not event:
    flash_check()
    return
  print(f'{event=}')
  label, keytype = layout[event.key_number]
  if not label or not keytype:
    return
  print(f'{keytype=} {label=}')
  if keytype == 'control':
    control[label] = event.pressed
    ctlled.value = OFFON[any(control.values())]
    print(control)
    return
  if not event.pressed:
    return
  if keytype != 'change':
    raise ValueError(keytype)
  flash(actled)
  if control['color']:
    select_color(label)
    print(selected)
    return
  for fkey in fmap:
    if control[fkey]:
      routine = fmap[fkey][label]
      if not routine:
        return
      cmdstr = codes['func', routine]
      break
  else:
    cmdstr = get_change_command(label)
  print(f'{cmdstr=}')
  serial.write(f'{cmdstr}\n'.encode())

def get_change_command(verb: str) -> str:
  what = get_what()
  if verb == 'clear':
    quantity = None
  else:
    quantity = 1
  cmdstr = codes[what, verb]
  if quantity:
    cmdstr += str(quantity)
  return cmdstr

def get_what() -> str:
  if control['pixel']:
    return 'pixel'
  elif control['brightness']:
    return 'brightness'
  return colors[selected['color']]

def select_color(verb: str) -> None:
  if verb == 'clear':
    value = 0
  else:
    value = selected['color']
    if verb == 'minus':
      value -= 1
    else:
      value += 1
    value -= len(colors) * (value // len(colors))
  selected['color'] = value

def init_led(pin: Pin) -> DigitalInOut:
  led = DigitalInOut(pin)
  led.direction = Direction.OUTPUT
  led.value = OFF
  return led

def flash(io: DigitalInOut, ms: int = 100) -> None:
  io.value = ON
  offat[io] = ticks_add(ticks_ms(), ms)

def flash_check() -> None:
  for io in offat:
    if io.value is ON and ticks_diff(ticks_ms(), offat[io]) >= 0:
      io.value = OFF

if __name__ == '__main__':
  main()
