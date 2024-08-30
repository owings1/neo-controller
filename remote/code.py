from __future__ import annotations

try:
  from typing import TYPE_CHECKING, Any, Iterator
except ImportError:
  TYPE_CHECKING = False
  pass

if TYPE_CHECKING:
  import defaults
  import defaults as settings
else:
  import defaults
  import settings
  settings.__dict__.update(
    (name, getattr(settings, name, getattr(defaults, name)))
    for name in defaults.__dict__)

import board
import busio
import keypad
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms
from digitalio import DigitalInOut, Direction
from microcontroller import Pin

from terms import *

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
run_presets = (
  ('func_draw', None),
  ('anim_wheel_loop', 2),
  ('anim_wheel_loop', 0),
  ('anim_state_loop', 2),
  ('anim_state_loop', 1),
  ('anim_state_loop', 0),
)
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
  serial = busio.UART(board.TX, None, baudrate=settings.baudrate)
  fnum = 0
  for label in settings.layout:
    if keytypes[label] == 'meta':
      meta[label] = False
      continue
    if keytypes[label] == 'control':
      control[label] = False
    fnums[label] = fnum
    fnum += 1
  keys = keypad.Keys(
    tuple(getattr(board, pin) for pin in settings.button_pins),
    value_when_pressed=False,
    pull=True)
  actled = init_led(board.LED_GREEN)
  ctlled = init_led(board.LED_BLUE)
  selected['color'] = 0
  idgen = cmdid_gen()
  send_command('func_noop', 'run', None)

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
  label = settings.layout[event.key_number]
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
        send_command(*get_meta_command(verb, label))
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
  for what in control:
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
    at=ticks_add(ticks_ms(), settings.repeat_threshold),
    func=send_command,
    args=cmd,
    interval=settings.repeat_interval)

  send_command(*cmd)

def get_meta_command(verb: str, label: str) -> tuple[str, str, int|None]:
  fnum = fnums[label]
  if verb == 'run':
    what, quantity = run_presets[fnum]
  elif ('state', verb) in CODES:
    what = 'state'
    quantity = fnum
  else:
    raise ValueError(verb)
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
    value = absindex(value, len(colors))
  selected['color'] = value

def send_command(what: str, verb: str, quantity: int|None) -> None:
  flash(actled)
  cmdstr = CODES[what, verb]
  if quantity is not None:
    cmdstr += str(quantity)
  cmd = f'{next(idgen)}{cmdstr}\n'.encode()
  print(f'{cmdstr=} {cmd=}')
  for _ in range(-1, settings.command_repetition):
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
  rem: set|None = None
  for io in offat:
    if io.value is ON and ticks_diff(ticks_ms(), offat[io]) >= 0:
      io.value = OFF
      rem = rem or set()
      rem.add(io)
  if rem:
    for io in rem:
      del(offat[io])

def repeat_check() -> None:
  if repeat and ticks_diff(ticks_ms(), repeat['at']) >= 0:
    repeat['at'] = ticks_add(repeat['at'], repeat['interval'])
    repeat['func'](*repeat['args'])

def cmdid_gen():
  ranges = tuple(
    range(ord(x), ord(y) + 1)
    for x, y in ('09', 'az', 'AZ'))
  while True:
    for r in ranges:
      yield from map(chr, r)

def absindex(i: int, length: int) -> int:
  try:
    return i - (length * (i // length))
  except ZeroDivisionError:
    raise IndexError

if __name__ == '__main__':
  main()
