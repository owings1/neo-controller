from __future__ import annotations

from defaults import *

try:
  from settings import *
except ImportError as e:
  print(f'Error loading settings: {type(e).__name__}: {e}')

from terms import *

try:
  from typing import Any, Iterator
except ImportError:
  pass

import board
import busio
import keypad
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms
from digitalio import DigitalInOut, Direction
from microcontroller import Pin

OFF, ON = OFFON = True, False

idgen: Iterator[str]|None = None
serial: busio.UART|None = None
actled: DigitalInOut|None = None
ctlled: DigitalInOut|None = None
keys: keypad.Keys|None = None
keytypes = {
  'clear': 'change',
  'minus': 'change',
  'plus': 'change',
  'color': 'control',
  'pixel': 'control',
  'hue': 'control',
  'restore': 'meta',
  'save': 'meta',
  'run': 'meta',
}
fnums: dict[str, int] = {}
control: dict[str, bool] = {}
meta: dict[str, bool] = {}
selected: dict[str, Any] = {}
offat: dict[DigitalInOut, int] = {}
repeat: dict[str, Any] = {}
colors = ('brightness', 'red', 'green', 'blue', 'white')

def main() -> None:
  try:
    init()
    while True:
      loop()
  finally:
    deinit()

def init() -> None:
  global actled, ctlled, idgen, keys, serial
  serial = busio.UART(board.TX, None, baudrate=baudrate)
  fnum = 0
  for label in layout:
    if keytypes[label] == 'meta':
      meta[label] = False
      continue
    if keytypes[label] == 'control':
      control[label] = False
    fnums[label] = fnum
    fnum += 1
  keys = keypad.Keys(
    tuple(getattr(board, pin) for pin in button_pins),
    value_when_pressed=False,
    pull=True)
  actled = init_led(board.LED_GREEN)
  ctlled = init_led(board.LED_BLUE)
  selected['color'] = 0
  idgen = cmdid_gen()
  send_command('func', 'noop', None)

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
  meta.clear()
  fnums.clear()
  selected.clear()
  repeat.clear()

def loop() -> None:
  event = keys.events.get()
  if not event:
    flash_check()
    repeat_check()
    return
  print(f'{event=}')
  repeat.clear()
  label = layout[event.key_number]
  keytype = keytypes[label]
  if not label or not keytype:
    return
  print(f'{keytype=} {label=}')

  if keytype == 'meta':
    meta[label] = event.pressed
    ctlled.value = OFFON[any(meta.values()) or any(control.values())]
    print(meta)
    return

  if event.pressed:
    for verb in meta:
      if meta[verb]:
        send_command(*get_func_command(verb, label))
        return

  if keytype == 'control':
    control[label] = event.pressed
    ctlled.value = OFFON[any(control.values())]
    print(control)
    return

  if not event.pressed:
    return

  if keytype != 'change':
    raise ValueError(keytype)

  verb = label
  for what in ('color', 'pixel', 'hue'):
    if control[what]:
      break
  else:
    what = colors[selected['color']]

  if what == 'color':
    do_select_color(verb)
    print(selected)
    return

  cmd = get_change_command(verb, what)
  repeat.update(
    at=ticks_add(ticks_ms(), repeat_threshold),
    func=send_command,
    args=cmd,
    interval=repeat_interval)

  send_command(*cmd)

def get_func_command(verb: str, label: str) -> tuple[str, str, int|None]:
  what = 'func'
  quantity = fnums[label]
  if quantity == 0:
    quantity = None
  return what, verb, quantity

def get_change_command(verb: str, what: str) -> tuple[str, str, int|None]:
  quantity = None if verb == 'clear' else 1
  return what, verb, quantity

def do_select_color(verb: str) -> None:
  flash(actled)
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

def send_command(what: str, verb: str, quantity: int|None) -> None:
  flash(actled)
  cmdstr = codes[what, verb]
  if quantity is not None:
    cmdstr += str(quantity)
  cmd = f'{next(idgen)}{cmdstr}\n'.encode()
  print(f'{cmdstr=} {cmd=}')
  for _ in range(command_repetition):
    serial.write(cmd)

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

def repeat_check() -> None:
  if repeat and ticks_diff(ticks_ms(), repeat['at']) >= 0:
    repeat['at'] += repeat['interval']
    repeat['func'](*repeat['args'])

def cmdid_gen():
  ranges = tuple(
    range(ord(x), ord(y) + 1)
    for x, y in ('09', 'az', 'AZ'))
  while True:
    for r in ranges:
      yield from map(chr, r)

if __name__ == '__main__':
  main()
