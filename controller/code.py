from __future__ import annotations

try:
  from typing import Any, Collection
except ImportError:
  import defaults
  import settings
  settings.__dict__.update(
    (name, getattr(settings, name, getattr(defaults, name)))
    for name in defaults.__dict__)
else:
  import defaults
  import defaults as settings

import math
import traceback

import board
import busio
import rgbutil
import utils
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms
from classes import ActLeds, BufferStore, SdReader
from neopixel import NeoPixel
from rainbowio import colorwheel

from terms import *

brightness_scale = 64

pixels: NeoPixel|None = None
sd: SdReader|None = None
serial: busio.UART|None = None
leds: ActLeds|None = None
bufstore: BufferStore|None = None
selected: dict[str, Any] = {}
anim: dict[str, Any] = {}

def main() -> None:
  try:
    init()
    while True:
      loop()
  finally:
    deinit()

def init() -> None:
  global pixels, sd, bufstore, serial, leds
  pixels = NeoPixel(
    getattr(board, settings.data_pin),
    settings.num_pixels,
    brightness=settings.initial_brightness / brightness_scale,
    auto_write=False,
    pixel_order=settings.pixel_order)
  sd = SdReader(getattr(board, settings.sd_cs_pin))
  sd.enabled = settings.sd_enabled
  sd.remount()
  bufstore = BufferStore(pixels, sd)
  bufstore.fallback_color = settings.initial_color
  AnimManager.init(pixels)
  serial = busio.UART(
    None,
    board.RX,
    baudrate=settings.baudrate,
    timeout=settings.serial_timeout)
  leds = ActLeds.frompins(board.LED_GREEN, board.LED_BLUE)
  selected['pixel'] = None
  selected['hue'] = None
  Command.init(serial, pixels)
  bufstore.restore(0)

def deinit() -> None:
  if serial:
    serial.deinit()
  if pixels:
    pixels.deinit()
  if leds:
    leds.deinit()
  if sd:
    sd.deinit()
  if bufstore:
    bufstore.deinit()
  AnimManager.deinit()
  Command.deinit()
  anim.clear()

def loop() -> None:
  cmdstr = Command.read()
  if not cmdstr:
    AnimManager.run()
    leds.run()
    return
  leds.act.flash()
  print(f'{cmdstr=}')
  try:
    cmd = Command.parse(cmdstr)
    print(f'{cmd=}')
    if cmd[0] != 'brightness':
      anim.clear()
    Command.do(*cmd)
  except Exception as err:
    traceback.print_exception(err)
    leds.err.flash()

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
        leds.err.flash()
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
    what, verb = ACTIONS[cmdstr[0]]
    if len(cmdstr) == 1:
      quantity = None
    else:
      quantity = int(cmdstr[1:])
    return what, verb, quantity

  @classmethod
  def do(self, what: str, verb: str, quantity: int|None) -> None:
    action = (what, verb)
    if action not in CODES:
      raise ValueError(action)
    if what in Change.whats:
      getattr(Change, what)(verb, quantity)
    elif what == 'state':
      if not bufstore.action(verb, quantity):
        leds.err.flash()
      if verb == 'restore':
        selected['hue'] = None
    elif verb == 'run':
      if what == 'func_draw':
        self.pixels.show()
      elif what == 'func_noop':
        pass
      elif what in AnimManager.routines:
        getattr(AnimManager, what)(quantity)
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
      value = math.ceil(pixels.brightness * brightness_scale) - quantity
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
      value = utils.absindex(value, length)
    return value

class AnimManager:

  speeds = settings.anim_speeds
  types = 'fill', 'each'
  routines = 'anim_wheel_loop', 'anim_state_loop'

  @classmethod
  def init(self, pixels: NeoPixel) -> None:
    self.pixels = pixels

  @classmethod
  def deinit(self) -> None:
    pass

  @classmethod
  def run(self):
    if not (anim and ticks_diff(ticks_ms(), anim['at']) >= 0):
      return
    if anim['type'] not in self.types:
      raise ValueError(anim['type'])
    func = getattr(self, anim['type'])
    try:
      func()
    except StopIteration:
      anim.clear()
    else:
      anim['at'] = ticks_add(anim['at'], anim['interval'])

  @classmethod
  def fill(self):
    value = next(anim['it'])
    if value != anim.get('current'):
      self.pixels.fill(value)
      self.pixels.show()
    anim['current'] = value

  @classmethod
  def each(self):
    change = False
    for p, it in enumerate(anim['its']):
      value = next(it)
      if change or self.pixels[p] != value:
        change = True
        self.pixels[p] = value
    if change:
      self.pixels.show()

  @classmethod
  def anim_wheel_loop(self, speed: int) -> None:
    anim.update(
      type='fill',
      at=ticks_ms(),
      interval=self.speeds[speed],
      it=rgbutil.transitions(
        path=(0xff0000, 0xff00, 0xff),
        steps=0x100 * (speed + 1),
        loop=True))

  @classmethod
  def anim_state_loop(self, speed: int) -> None:
    buffers = map(bufstore.read, range(6))
    buffers = filter(None, buffers)
    buffers = tuple(map(tuple, buffers))
    if len(buffers) < 2:
      raise ValueError('not enough buffers')
    anim.update(
      type='each',
      at=ticks_ms(),
      interval=self.speeds[speed],
      its=tuple(
        rgbutil.transitions(
          tuple(values[p] for values in buffers),
          steps=0x100 * (speed + 1),
          loop=True)
        for p in range(self.pixels.n)))


if __name__ == '__main__':
  main()
