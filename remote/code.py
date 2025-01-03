from __future__ import annotations

import board
import busio
import keypad
import utils
from digitalio import DigitalInOut
from utils import Command, Repeater, settings

from common import Led
from terms import *

class App:
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
  fnums: dict[str, int]|None = None
  control: dict[str, bool]|None = None
  meta: dict[str, bool]|None = None
  selected: dict[str, Any]|None = None
  offat: dict[DigitalInOut, int]|None = None
  repeat: dict[str, Any]|None = None
  colors = ('brightness', 'red', 'green', 'blue', 'white')
  repeater: Repeater|None = None

  def main(self) -> None:
    try:
      self.init()
      while True:
        self.loop()
    except KeyboardInterrupt:
      print(f'Stopping from Ctrl-C')
    finally:
      self.deinit()

  def init(self) -> None:
    self.deinit()
    self.fnums = {}
    self.control = {}
    self.meta = {}
    self.selected = {}
    self.offat = {}
    self.repeat = {}
    self.serial = busio.UART(board.TX, None, baudrate=settings.baudrate)
    fnum = 0
    for label in settings.layout:
      if self.keytypes[label] == 'meta':
        self.meta[label] = False
        continue
      if self.keytypes[label] == 'control':
        self.control[label] = False
      self.fnums[label] = fnum
      fnum += 1
    self.keys = keypad.Keys(
      tuple(getattr(board, pin) for pin in settings.button_pins),
      value_when_pressed=False,
      pull=True)
    self.actled = Led(board.LED_GREEN)
    self.ctlled = Led(board.LED_BLUE)
    self.repeater = Repeater(self.send_command)
    self.selected['color'] = 0
    self.idgen = utils.cmdid_gen()
    self.send_command(Command('func_noop', 'run', None))

  def deinit(self) -> None:
    if self.serial:
      self.serial.deinit()
    if self.keys:
      self.keys.deinit()
    if self.actled:
      self.actled.deinit()
    if self.ctlled:
      self.ctlled.deinit()
    if self.repeater:
      self.repeater.deinit()
    if self.offat:
      self.offat.clear()
    if self.control:
      self.control.clear()
    if self.meta:
      self.meta.clear()
    if self.fnums:
      self.fnums.clear()
    if self.selected:
      self.selected.clear()

  def loop(self) -> None:
    event = self.keys.events.get()
    if not event:
      self.actled.run()
      self.ctlled.run()
      self.repeater.run()
      return
    self.repeater.clear()
    self.handle(event)

  def handle(self, event: keypad.Event) -> None:
    label = settings.layout[event.key_number]
    keytype = self.keytypes[label]
    if not label or not keytype:
      return

    if keytype == 'meta':
      self.meta[label] = event.pressed
      self.ctlled.set(any(self.meta.values()) or any(self.control.values()))
      print(self.meta)
      return

    if event.pressed:
      for verb in self.meta:
        if self.meta[verb]:
          cmd = self.get_meta_command(verb, label)
          if cmd.what == 'speed' and cmd.verb != 'clear':
            self.repeater.schedule(cmd)
          self.send_command(cmd)
          return

    if keytype == 'control':
      self.control[label] = event.pressed
      self.ctlled.set(any(self.control.values()))
      print(self.control)
      return

    if not event.pressed:
      return

    if keytype != 'change':
      raise ValueError(keytype)

    verb = label
    for what in self.control:
      if self.control[what]:
        break
    else:
      what = self.colors[self.selected['color']]

    if what == 'color':
      self.do_select_color(verb)
      print(self.selected)
      return

    cmd = self.get_change_command(verb, what)
    self.repeater.schedule(cmd)
    self.send_command(cmd)

  def get_meta_command(self, verb: str, label: str) -> Command:
    fnum = self.fnums[label]
    if verb == 'run':
      what, verb, quantity = self.run_presets[fnum]
    elif ('buffer', verb) in CODES:
      if self.meta['restore'] and self.meta['save']:
        verb = 'clear'
      print(f'{verb=} meta={self.meta}')
      what = 'buffer'
      quantity = fnum
    else:
      raise ValueError(verb)
    return Command(what, verb, quantity)

  def get_change_command(self, verb: str, what: str) -> Command:
    quantity = None if verb == 'clear' else 1
    if quantity and settings.reverse_pixel_dir:
      quantity = -quantity
    return Command(what, verb, quantity)

  def do_select_color(self, verb: str) -> None:
    self.actled.flash()
    if verb == 'clear':
      value = 0
    else:
      value = self.selected['color']
      if verb == 'minus':
        value -= 1
      else:
        value += 1
      value = utils.absindex(value, len(self.colors))
    self.selected['color'] = value

  def send_command(self, cmd: Command) -> None:
    self.actled.flash()
    print(f'{cmd=}')
    cmdstr = CODES[cmd.what, cmd.verb]
    if cmd.quantity is not None:
      cmdstr += str(cmd.quantity)
    cmd = f'{next(self.idgen)}{cmdstr}\n'.encode()
    for _ in range(-1, settings.command_redundancy):
      self.serial.write(cmd)

app = App()

del(App)

if __name__ == '__main__':
  app.main()

# IDE Environment
try:
  from typing import Any, Iterator
except ImportError:
  pass
