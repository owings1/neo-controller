from __future__ import annotations

import board
import busio
import keypad
import utils
from digitalio import DigitalInOut
from utils import Command, Repeater, settings

from common import Led
from terms import *

try:
  from typing import Any, Iterator
except ImportError:
  pass

idgen: Iterator[str]|None = None
serial: busio.UART|None = None
actled: Led|None = None
ctlled: Led|None = None
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
  ('anim_wheel_loop', 'run', None),
  ('anim_buffers_loop', 'run', None),
  ('anim_marquee_loop', 'run', None),
  ('speed', 'clear', None),
  ('speed', 'minus', 1),
  ('speed', 'plus', 1),
)
fnums: dict[str, int] = {}
control: dict[str, bool] = {}
meta: dict[str, bool] = {}
selected: dict[str, Any] = {}
offat: dict[DigitalInOut, int] = {}
repeat: dict[str, Any] = {}
colors = ('brightness', 'red', 'green', 'blue', 'white')
repeater: Repeater|None = None

def main() -> None:
  try:
    init()
    while True:
      loop()
  finally:
    deinit()

def init() -> None:
  global actled, ctlled, idgen, keys, repeater, serial
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
  actled = Led(board.LED_GREEN)
  ctlled = Led(board.LED_BLUE)
  repeater = Repeater(send_command)
  selected['color'] = 0
  idgen = utils.cmdid_gen()
  send_command(Command('func_noop', 'run', None))

def deinit() -> None:
  if serial:
    serial.deinit()
  if keys:
    keys.deinit()
  if actled:
    actled.deinit()
  if ctlled:
    ctlled.deinit()
  if repeater:
    repeater.deinit()
  offat.clear()
  control.clear()
  meta.clear()
  fnums.clear()
  selected.clear()

def loop() -> None:
  event = keys.events.get()
  if not event:
    actled.run()
    ctlled.run()
    repeater.run()
    return
  repeater.clear()
  handle(event)

def handle(event: keypad.Event) -> None:
  label = settings.layout[event.key_number]
  keytype = keytypes[label]
  if not label or not keytype:
    return

  if keytype == 'meta':
    meta[label] = event.pressed
    ctlled.set(any(meta.values()) or any(control.values()))
    print(meta)
    return

  if event.pressed:
    for verb in meta:
      if meta[verb]:
        cmd = get_meta_command(verb, label)
        if cmd.what == 'speed' and cmd.verb != 'clear':
          repeater.schedule(cmd)
        send_command(cmd)
        return

  if keytype == 'control':
    control[label] = event.pressed
    ctlled.set(any(control.values()))
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
  repeater.schedule(cmd)
  send_command(cmd)

def get_meta_command(verb: str, label: str) -> Command:
  fnum = fnums[label]
  if verb == 'run':
    what, verb, quantity = run_presets[fnum]
  elif ('buffer', verb) in CODES:
    if meta['restore'] and meta['save']:
      verb = 'clear'
    print(f'{verb=} {meta=}')
    what = 'buffer'
    quantity = fnum
  else:
    raise ValueError(verb)
  return Command(what, verb, quantity)

def get_change_command(verb: str, what: str) -> Command:
  quantity = None if verb == 'clear' else 1
  if quantity and settings.reverse_pixel_dir:
    quantity = -quantity
  return Command(what, verb, quantity)

def do_select_color(verb: str) -> None:
  actled.flash()
  if verb == 'clear':
    value = 0
  else:
    value = selected['color']
    if verb == 'minus':
      value -= 1
    else:
      value += 1
    value = utils.absindex(value, len(colors))
  selected['color'] = value

def send_command(cmd: Command) -> None:
  actled.flash()
  print(f'{cmd=}')
  cmdstr = CODES[cmd.what, cmd.verb]
  if cmd.quantity is not None:
    cmdstr += str(cmd.quantity)
  cmd = f'{next(idgen)}{cmdstr}\n'.encode()
  for _ in range(-1, settings.command_repetition):
    serial.write(cmd)

if __name__ == '__main__':
  main()
