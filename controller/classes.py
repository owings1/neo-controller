from __future__ import annotations

import math
import os
import traceback
from collections import namedtuple

import board
import busio
import sdcardio
import storage
import utils
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms
from digitalio import DigitalInOut, Direction
from microcontroller import Pin
from neopixel import NeoPixel
from rainbowio import colorwheel
from utils import ColorType, settings

import terms

try:
  from typing import Collection, Iterator, Self, Sequence
except ImportError:
  pass

class Commander:

  serial: busio.UART
  pixels: NeoPixel
  bufstore: BufStore
  animator: Animator
  leds: ActLeds
  changer: Changer
  lastid: str|None

  def __init__(self, serial: busio.UART, pixels: NeoPixel, bufstore: BufStore, animator: Animator, leds: ActLeds) -> None:
    self.serial = serial
    self.pixels = pixels
    self.bufstore = bufstore
    self.animator = animator
    self.leds = leds
    self.changer = Changer(self.pixels)
    self.lastid = None

  def deinit(self) -> None:
    self.changer.deinit()

  def read(self) -> str|None:
    cmdstr = self.serial.in_waiting and self.serial.readline()
    if not cmdstr:
      return
    cmdstr = cmdstr.strip(b'\x00')
    try:
      cmdstr = str(cmdstr, 'utf-8').strip()
    except UnicodeError as err:
      traceback.print_exception(err)
      self.leds.err.flash()
      return
    if cmdstr:
      if cmdstr[0] == self.lastid:
        cmdstr = None
      else:
        self.lastid = cmdstr[0]
        cmdstr = cmdstr[1:]
        print(f'cmdid={self.lastid}')
    return cmdstr or None

  def parse(self, cmdstr: str) -> tuple[str, str, int|None]:
    what, verb = terms.ACTIONS[cmdstr[0]]
    if len(cmdstr) == 1:
      quantity = None
    else:
      quantity = int(cmdstr[1:])
    return what, verb, quantity

  def do(self, what: str, verb: str, quantity: int|None) -> None:
    action = (what, verb)
    if action not in terms.CODES:
      raise ValueError(action)
    if what in self.changer.whats:
      getattr(self.changer, what)(verb, quantity)
    elif what == 'state':
      if not self.bufstore.action(verb, quantity):
        self.leds.err.flash()
      if verb == 'restore':
        self.changer.selected['hue'] = None
    elif verb == 'run':
      if what == 'func_draw':
        self.pixels.show()
      elif what == 'func_noop':
        pass
      elif what in self.animator.routines:
        getattr(self.animator, what)(quantity)
      else:
        raise ValueError(action)
    else:
      raise ValueError(action)

class Changer:

  whats = (
    'pixel',
    'hue',
    'brightness',
    'red',
    'green',
    'blue',
    'white')

  pixels: NeoPixel
  selected: dict[str, int|None]

  def __init__(self, pixels: NeoPixel) -> None:
    self.pixels = pixels
    self.selected = dict.fromkeys(('pixel', 'hue'))

  def deinit(self) -> None:
    for key in self.selected:
      self.selected[key] = None

  def pixel(self, verb: str, quantity: int|None) -> None:
    value = self.index_resolve(verb, quantity, self.selected['pixel'], self.pixels.n)
    self.selected.update(pixel=value, hue=None)
    print(f'selected={self.selected}')

  def hue(self, verb: str, quantity: int|None) -> None:
    prange = self.prange()
    if self.selected['hue'] is None and quantity is not None:
      current = utils.unwheel(self.pixels[next(iter(prange))])
    else:
      current = self.selected['hue']
    value = self.index_resolve(verb, quantity, current, 0x100)
    hue = utils.as_tuple(colorwheel(value or 0))
    for p in prange:
      self.pixels[p] = hue
    self.pixels.show()
    self.selected['hue'] = value
    print(f'selected={self.selected}')

  def brightness(self, verb: str, quantity: int|None) -> None:
    if verb == 'clear':
      value = settings.initial_brightness
    elif verb == 'set':
      value = quantity
    elif verb == 'minus':
      value = math.ceil(self.pixels.brightness * settings.brightness_scale) - quantity
    else:
      value = int(self.pixels.brightness * settings.brightness_scale) + quantity
    value = max(0, min(settings.brightness_scale, value)) / settings.brightness_scale
    change = value != self.pixels.brightness
    print(f'brightness={self.pixels.brightness} {change=}')
    if change:
      self.pixels.brightness = value
      self.pixels.show()

  def color(color: str, indexes: Collection[int]):
    def wrapper(self: Self, verb: str, quantity: int|None) -> None:
      if quantity is not None:
        if verb == 'minus':
          quantity *= -1
      change = False
      initial = utils.as_tuple(settings.initial_color)
      for p in self.prange():
        values = list(self.pixels[p])
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
          self.pixels[p] = tuple(values)
          change = True
          print(f'{p=} {self.pixels[p]}')
      if change:
        self.pixels.show()
      self.selected['hue'] = None
    return wrapper

  red = color('red', (0,))
  green = color('green', (1,))
  blue = color('blue', (2,))
  white = color('white', range(3))

  del(color)

  def prange(self) -> Collection[int]:
    if self.selected['pixel'] is None:
      return range(self.pixels.n)
    return (self.selected['pixel'],)

  @staticmethod
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

class BufStore:

  actions = 'restore', 'save', 'clear'

  subdir: str = 'buffers'
  fallback_color: ColorType = 0xffffff

  def __init__(self, pixels: NeoPixel, sd: SdReader, size: int) -> None:
    self.pixels = pixels
    self.sd = sd
    self.size = size
    self._range = range(self.size)

  def deinit(self) -> None:
    pass

  def action(self, verb: str, index: int) -> bool:
    if verb in self.actions:
      func = getattr(self, verb)
    else:
      raise ValueError(verb)
    return bool(func(index))

  def restore(self, index: int) -> bool:
    it = self.read(index)
    if not it:
      self.pixels.fill(self.fallback_color)
      self.pixels.show()
      return False
    change = False
    for p, value in enumerate(it):
      if change or self.pixels[p] != utils.as_tuple(value):
        change = True
        self.pixels[p] = value
    if change:
      self.pixels.show()
    return True

  def save(self, index: int) -> bool:
    if index not in self._range:
      raise IndexError
    if not self.sd.mkdirp(self.subdir):
      return False
    try:
      with open(self.file(index), 'w') as file:
        for p, value in enumerate(self.pixels):
          if p:
            file.write('\n')
          file.write(hex(utils.as_int(value)))
    except OSError as err:
      traceback.print_exception(err)
      return False
    return True

  def clear(self, index: int) -> bool:
    if index not in self._range:
      raise IndexError
    if not self.sd.checkmount():
      return False
    try:
      os.remove(self.file(index))
    except OSError as err:
      if err.errno != 2:
        traceback.print_exception(err)
        return False
    return True

  def has(self, index: int) -> bool:
    if index not in self._range:
      return False
    if self.sd.checkmount():
      try:
        next(self._reader(self.file(index), 1))
      except (OSError, ValueError, StopIteration) as err:
        traceback.print_exception(err)
      else:
        return True
    return False

  def read(self, index: int) -> Iterator[int]|None:
    if self.pixels.n > 0 and self.has(index):
        return self._reader(self.file(index), self.pixels.n)

  def _reader(self, file: str, stop: int) -> Iterator[int]:
    i = 0
    with open(file) as f:
      while True:
        line = f.readline()
        while line:
          line = line.strip()
          if line:
            yield int(line)
            i += 1
            if i == stop:
              return
          line = f.readline()
        if i == 0:
          # empty file
          return
        f.seek(0)

  def file(self, index: int) -> str:
    if index not in self._range:
      raise IndexError
    return f'{self.sd.path}/{self.subdir}/s{index:03}'

class SdReader:

  card: sdcardio.SDCard|None
  vfs: storage.VfsFat|None

  @property
  def checkfile(self) -> str:
    return f'{self.path}/.mountcheck'

  def __init__(self, cs: Pin, *, path: str = '/sd') -> None:
    self.cs = cs
    self.path = path
    self.card = None
    self.vfs = None
    self.enabled = True

  def deinit(self) -> None:
    self.umount()

  def checkmount(self) -> bool:
    if self.card:
      try:
        open(self.checkfile).close()
        return True
      except OSError:
        pass
    return self.remount()

  def remount(self) -> bool:
    if not self.enabled:
      return False
    self.umount()
    try:
      self.card = sdcardio.SDCard(board.SPI(), self.cs)
      self.vfs = storage.VfsFat(self.card)
      storage.mount(self.vfs, self.path)
      open(self.checkfile, 'w').close()
    except OSError as err:
      traceback.print_exception(err)
      self.umount()
      return False
    return True

  def umount(self) -> None:
    if self.card:
      try:
        storage.umount(self.path)
      except OSError:
        pass
      self.card.deinit()
      self.card = None
      self.vfs = None

  def mkdirp(self, path: str) -> bool:
    if not path:
      return ValueError(path)
    if not self.checkmount():
      return False
    try:
      stat = self.vfs.stat(path)
    except OSError as err:
      if err.errno != 2:
        traceback.print_exception(err)
        return False
    else:
      if (stat[0] & 0x4000) == 0x4000:
        return True
      err = Exception(f'{path} not a directory {stat=}')
      traceback.print_exception(err)
      return False
    nodes = path.split('/')
    nodes.reverse()
    try:
      cur = nodes.pop()
      self.vfs.mkdir(cur)
      for node in nodes:
        cur += f'/{node}'
        self.vfs.mkdir(cur)
    except OSError as err:
      traceback.print_exception(err)
      return False
    return True

class Led:

  OFF = True
  ON = False

  off_at: int|None

  def __init__(self, pin: Pin) -> None:
    self.io = DigitalInOut(pin)
    self.io.direction = Direction.OUTPUT
    self.io.value = self.OFF
    self.off_at = None

  def deinit(self):
    self.io.deinit()

  def flash(self, duration: int = 100) -> None:
    self.io.value = self.ON
    self.off_at = ticks_add(ticks_ms(), duration)

  def run(self) -> None:
    if self.off_at is not None and self.io.value is self.ON:
      if ticks_diff(ticks_ms(), self.off_at) >= 0:
        self.io.value = self.OFF
        self.off_at = None

class ActLeds(namedtuple('LedsBase', ('act', 'err'))):
  act: Led
  err: Led

  def run(self) -> None:
    for led in self:
      led.run()

  def deinit(self) -> None:
    for led in self:
      led.deinit()

  @classmethod
  def frompins(cls, *pins) -> Self:
    return cls(*map(Led, pins))

class Animation:
  interval: int
  at: int

  def ready(self) -> None:
    return ticks_diff(ticks_ms(), self.at) >= 0

  def run(self, pixels: NeoPixel) -> None:
    raise NotImplementedError

class FillAnimation(Animation):

  def __init__(self, it: Iterator[ColorType], interval: int, at: int|None = None) -> None:
    self.it = it
    self.interval = interval
    self.at = ticks_ms() if at is None else at
    self.current = None

  def run(self, pixels: NeoPixel) -> None:
    value = next(self.it)
    if value != self.current:
      pixels.fill(value)
      pixels.show()
      self.current = value
    self.at = ticks_add(ticks_ms(), self.interval)

class BufAnimation(Animation):

  def __init__(self, its: Sequence[Iterator[ColorType]], interval: int, at: int|None = None) -> None:

    self.its = its
    self.interval = interval
    self.at = ticks_ms() if at is None else at

  def run(self, pixels: NeoPixel) -> None:
    change = False
    for p, it in enumerate(self.its):
      value = next(it)
      if change or pixels[p] != value:
        change = True
        pixels[p] = value
    if change:
      pixels.show()
    self.at = ticks_add(ticks_ms(), self.interval)

class Animator:

  speeds = settings.anim_speeds
  routines = 'anim_wheel_loop', 'anim_state_loop'

  pixels: NeoPixel
  bufstore: BufStore
  anim: Animation|None = None
  
  def __init__(self, pixels: NeoPixel, bufstore: BufStore) -> None:
    self.pixels = pixels
    self.bufstore = bufstore

  def deinit(self) -> None:
    self.clear()

  def run(self):
    if self.anim and self.anim.ready():
      try:
        self.anim.run(self.pixels)
      except StopIteration:
        self.clear()

  def clear(self) -> None:
    self.anim = None

  def anim_wheel_loop(self, speed: int) -> None:
    it=utils.transitions(
        path=(0xff0000, 0xff00, 0xff),
        steps=0x100 * (speed + 1),
        loop=True)
    self.anim = FillAnimation(it, self.speeds[speed])

  def anim_state_loop(self, speed: int) -> None:
    bufs = map(self.bufstore.read, range(self.bufstore.size))
    bufs = filter(None, bufs)
    bufs = tuple(map(tuple, bufs))
    if len(bufs) < 2:
      raise ValueError('not enough buffers')
    its = tuple(
      utils.transitions(
        tuple(values[p] for values in bufs),
        steps=0x100 * (speed + 1),
        loop=True)
      for p in range(self.pixels.n))
    self.anim = BufAnimation(its, self.speeds[speed])

__all__ = tuple(cls.__name__ for cls in (
  Commander,
  BufStore,
  SdReader,
  ActLeds,
  Animator))