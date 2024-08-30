from __future__ import annotations

try:
  from typing import TYPE_CHECKING, Any, Collection, Iterable, Iterator
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
  
import os
import traceback
from math import ceil

import board
import busio
import neopixel
import rgbutil
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms
from digitalio import DigitalInOut, Direction
from microcontroller import Pin
from neopixel import NeoPixel
from rainbowio import colorwheel
from sdcard import SDcard

from terms import *

OFF, ON = OFFON = True, False

brightness_scale = 64
pixels: NeoPixel|None = None
serial: busio.UART|None = None
actled: DigitalInOut|None = None
errled: DigitalInOut|None = None
selected: dict[str, Any] = {}
anim: dict[str, Any] = {}
sd = SDcard(
  getattr(board, settings.sd_cs_pin),
  enabled=settings.sd_enabled)

def main() -> None:
  try:
    init()
    while True:
      loop()
  finally:
    deinit()

def init() -> None:
  global actled, errled, pixels, serial
  serial = busio.UART(
    None,
    board.RX,
    baudrate=settings.baudrate,
    timeout=settings.serial_timeout)
  pixels = neopixel.NeoPixel(
    getattr(board, settings.data_pin),
    settings.num_pixels,
    brightness=settings.initial_brightness / brightness_scale,
    auto_write=False,
    pixel_order=settings.pixel_order)
  actled = Led.init(board.LED_GREEN)
  errled = Led.init(board.LED_BLUE)
  sd.init()
  selected['pixel'] = None
  selected['hue'] = None
  Command.init(serial, pixels)
  State.init(sd, pixels)
  State.restore(0)

def deinit() -> None:
  if serial:
    serial.deinit()
  if pixels:
    pixels.deinit()
  if actled:
    actled.deinit()
  if errled:
    errled.deinit()
  sd.deinit()
  Command.deinit()
  State.deinit()
  anim.clear()
  Led.offat.clear()

def loop() -> None:
  cmdstr = Command.read()
  if not cmdstr:
    Anim.run()
    Led.run()
    return
  Led.flash(actled)
  print(f'{cmdstr=}')
  try:
    cmd = Command.parse(cmdstr)
    print(f'{cmd=}')
    if cmd[0] != 'brightness':
      anim.clear()
    Command.do(*cmd)
  except Exception as err:
    traceback.print_exception(err)
    Led.flash(errled)

class Command:

  serial: busio.UART
  pixels: NeoPixel
  lastid: str|None

  @classmethod
  def init(self, serial: busio.UART, pixels: NeoPixel) -> None:
    self.serial = serial
    self.pixels = pixels
    self.lastid = None

  @classmethod
  def deinit(self) -> None:
    pass

  @classmethod
  def read(self) -> str|None:
    cmdstr = self.serial.in_waiting and self.serial.readline()
    if cmdstr:
      cmdstr = cmdstr.strip(b'\x00')
      try:
        cmdstr = str(cmdstr, 'utf-8').strip()
      except UnicodeError as err:
        traceback.print_exception(err)
        Led.flash(errled)
        return
      if cmdstr:
        if cmdstr[0] == self.lastid:
          cmdstr = None
        else:
          self.lastid = cmdstr[0]
          cmdstr = cmdstr[1:]
          print(f'cmdid={self.lastid}')
    return cmdstr or None

  @classmethod
  def parse(self, cmdstr: str) -> tuple[str, str, int|None]:
    what, verb = actions[cmdstr[0]]
    if len(cmdstr) == 1:
      quantity = None
    else:
      quantity = int(cmdstr[1:])
    return what, verb, quantity

  @classmethod
  def do(self, what: str, verb: str, quantity: int|None) -> None:
    action = (what, verb)
    if action not in codes:
      raise ValueError(action)
    if what in Change.whats:
      getattr(Change, what)(verb, quantity)
    elif what == 'state':
      if not State.action(verb, quantity):
        Led.flash(errled)
      if verb == 'restore':
        selected['hue'] = None
    elif verb == 'run':
      if what == 'func_draw':
        self.pixels.show()
      elif what == 'func_noop':
        pass
      elif what in Anim.routines:
        getattr(Anim, what)(quantity)
      else:
        raise ValueError(action)
    else:
      raise ValueError(action)

class Change:

  whats = (
    'pixel',
    'hue',
    'brightness',
    'red',
    'green',
    'blue',
    'white')

  def pixel(verb: str, quantity: int|None) -> None:
    value = Change.index_resolve(verb, quantity, selected['pixel'], pixels.n)
    selected['pixel'] = value
    selected['hue'] = None
    print(f'{selected=}')

  def hue(verb: str, quantity: int|None) -> None:
    prange = Change.prange()
    if selected['hue'] is None and quantity is not None:
      current = rgbutil.wheel_reverse(*pixels[next(iter(prange))])
    else:
      current = selected['hue']
    value = Change.index_resolve(verb, quantity, current, 0x100)
    hue = rgbutil.as_tuple(colorwheel(value or 0))
    for p in prange:
      pixels[p] = hue
    pixels.show()
    selected['hue'] = value
    print(f'{selected=}')

  def brightness(verb: str, quantity: int|None) -> None:
    if verb == 'clear':
      value = settings.initial_brightness
    elif verb == 'set':
      value = quantity
    elif verb == 'minus':
      value = ceil(pixels.brightness * brightness_scale) - quantity
    else:
      value = int(pixels.brightness * brightness_scale) + quantity
    value = max(0, min(brightness_scale, value)) / brightness_scale
    change = value != pixels.brightness
    print(f'brightness={pixels.brightness} {change=}')
    if change:
      pixels.brightness = value
      pixels.show()

  def color(color: str, indexes: Collection[int]):
    def wrapper(verb: str, quantity: int|None) -> None:
      if quantity is not None:
        if verb == 'minus':
          quantity *= -1
      change = False
      initial = rgbutil.as_tuple(settings.initial_color)
      for p in Change.prange():
        values = list(pixels[p])
        pchange = False
        for b in indexes:
          if verb == 'clear' or quantity is None:
            value = initial[b]
          elif verb == 'set':
            value = quantity
          else:
            value = values[b] + quantity
          value = max(0, min(0xff, value))
          pchange |= values[b] != value
          values[b] = value
        if pchange:
          pixels[p] = tuple(values)
          change = True
          print(f'{p=} {pixels[p]}')
      if change:
        pixels.show()
      selected['hue'] = None
    return wrapper

  red = color('red', (0,))
  green = color('green', (1,))
  blue = color('blue', (2,))
  white = color('white', range(3))

  del(color)

  def prange() -> Collection[int]:
    if selected['pixel'] is None:
      return range(pixels.n)
    return (selected['pixel'],)

  def index_resolve(verb: str, quantity: int|None, current: int|None, length: int) -> int|None:
    if verb == 'clear' or quantity is None:
      value = None
    elif verb == 'set':
      if quantity < 0:
        quantity += length
      if 0 <= quantity < length:
        value = quantity
      else:
        raise IndexError(quantity)
    else:
      value = current
      if verb == 'minus':
        quantity *= -1
      if value is None:
        value = 0
        if quantity > 0:
          quantity -= 1
      value += quantity
      value = absindex(value, length)
    return value

class State:

  actions = 'restore', 'save', 'clear'
  subdir = 'states'

  @classmethod
  def init(self, sd: SDcard, pixels: NeoPixel) -> None:
    self.sd = sd
    self.pixels = pixels

  @classmethod
  def deinit(self) -> None:
    pass

  @classmethod
  def action(self, verb: str, index: int) -> bool:
    if verb in self.actions:
      func = getattr(State, verb)
    else:
      raise ValueError(verb)
    return bool(func(index))

  @classmethod
  def restore(self, index: int) -> bool:
    values = self.read(index)
    if not values:
      self.pixels.fill(settings.initial_color)
      self.pixels.show()
      return False
    change = False
    length = len(values)
    for p in range(self.pixels.n):
      value = values[absindex(p, length)]
      if change or self.pixels[p] != value:
        change = True
        self.pixels[p] = value
    if change:
      self.pixels.show()
    return True

  @classmethod
  def save(self, index: int) -> bool:
    if not self.sd.mkdirp(self.subdir):
      return False
    text = '\n'.join(self.pack())
    try:
      with open(self.file(index), 'w') as file:
        file.write(text)
    except OSError as err:
      traceback.print_exception(err)
      return False
    return True

  @classmethod
  def clear(self, index: int) -> bool:
    if not self.sd.check():
      return False
    try:
      os.remove(self.file(index))
    except OSError as err:
      if err.errno != 2:
        traceback.print_exception(err)
        return False
    return True

  @classmethod
  def read(self, index: int) -> tuple[int, tuple[int, ...]]|None:
    if self.sd.check():
      try:
        with open(self.file(index)) as file:
          text = file.read().strip()
        return tuple(self.unpack(text.splitlines()))
      except (OSError, ValueError) as err:
        traceback.print_exception(err)

  @classmethod
  def pack(self) -> Iterator[str]:
    return map(hex, map(rgbutil.as_int, self.pixels))

  @classmethod
  def unpack(self, packed: Iterable[str]) -> Iterator[tuple[int, int, int]]:
    for i, line in enumerate(packed):
      if i >= self.pixels.n:
        break
      if line.startswith('0x'):
        value = rgbutil.as_tuple(int(line))
      else:
        value = tuple(map(int, line.split(',', 2)))
      yield value

  @classmethod
  def file(self, index: int) -> str:
    return f'{self.sd.path}/{self.subdir}/s{index:03}'

class Anim:

  speeds = settings.anim_speeds
  types = 'fill', 'each'
  routines = 'anim_wheel_loop', 'anim_state_loop'

  def run():
    if not (anim and ticks_diff(ticks_ms(), anim['at']) >= 0):
      return
    if anim['type'] not in Anim.types:
      raise ValueError(anim['type'])
    func = getattr(Anim, anim['type'])
    try:
      func()
    except StopIteration:
      anim.clear()
    else:
      anim['at'] = ticks_add(anim['at'], anim['interval'])

  def fill():
    value = next(anim['it'])
    if value != anim.get('current'):
      pixels.fill(value)
      pixels.show()
    anim['current'] = value

  def each():
    change = False
    for p, it in enumerate(anim['its']):
      value = next(it)
      if change or pixels[p] != value:
        change = True
        pixels[p] = value
    if change:
      pixels.show()

  def anim_wheel_loop(speed: int) -> None:
    anim.update(
      type='fill',
      at=ticks_ms(),
      interval=Anim.speeds[speed],
      it=rgbutil.transitions(
        path=(0xff0000, 0xff00, 0xff),
        steps=0x100 * (speed + 1),
        loop=True))

  def anim_state_loop(speed: int) -> None:
    states = tuple(filter(None, map(State.read, range(6))))
    if len(states) < 2:
      raise ValueError('not enough states')
    anim.update(
      type='each',
      at=ticks_ms(),
      interval=Anim.speeds[speed],
      its=tuple(
        rgbutil.transitions(
          tuple(state[1][p] for state in states),
          steps=0x100 * (speed + 1),
          loop=True)
        for p in range(pixels.n)))

class Led:

  offat: dict[DigitalInOut, int] = {}

  def init(pin: Pin) -> DigitalInOut:
    led = DigitalInOut(pin)
    led.direction = Direction.OUTPUT
    led.value = OFF
    return led

  def flash(io: DigitalInOut, ms: int = 100) -> None:
    io.value = ON
    Led.offat[io] = ticks_add(ticks_ms(), ms)

  def run() -> None:
    rem: set|None = None
    for io in Led.offat:
      if io.value is ON and ticks_diff(ticks_ms(), Led.offat[io]) >= 0:
        io.value = OFF
        rem = rem or set()
        rem.add(io)
    if rem:
      for io in rem:
        del(Led.offat[io])

def absindex(i: int, length: int) -> int:
  try:
    return i - (length * (i // length))
  except ZeroDivisionError:
    raise IndexError

if __name__ == '__main__':
  main()
