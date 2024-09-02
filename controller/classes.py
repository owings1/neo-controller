from __future__ import annotations

import math
import os
import traceback
from collections import namedtuple

import busio
import defaults
import sdcardio
import storage
import utils
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms
from digitalio import DigitalInOut, Direction
from microcontroller import Pin
from neopixel import NeoPixel
from rainbowio import colorwheel
from utils import ColorType

import terms

try:
  from typing import ClassVar, Collection, Iterable, Iterator, Self, Sequence
except ImportError:
  pass

__all__ = (
'ActLeds',
'Animator',
'BufStore',
'Changer',
'Commander',
'SdReader')

class Commander:

  serial: busio.UART
  leds: ActLeds
  lastid: str|None = None

  def __init__(self, serial: busio.UART, leds: ActLeds) -> None:
    self.serial = serial
    self.leds = leds

  def deinit(self) -> None:
    pass

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
    if not cmdstr:
      return
    cmdid = cmdstr[0]
    if cmdid == self.lastid:
      return
    print(f'{cmdid=}')
    cmdstr = cmdstr[1:]
    self.lastid = cmdid
    return cmdstr or None

  def parse(self, cmdstr: str) -> tuple[str, str, int|None]:
    what, verb = terms.ACTIONS[cmdstr[0]]
    if len(cmdstr) == 1:
      quantity = None
    else:
      quantity = int(cmdstr[1:])
    return what, verb, quantity

class Changer:

  whats: ClassVar[Collection[str]] = (
    'pixel',
    'hue',
    'brightness',
    'red',
    'green',
    'blue',
    'white')
  brightness_scale: ClassVar[int] = defaults.brightness_scale
  initial_brightness: ClassVar[int] = defaults.initial_brightness
  initial_color: ClassVar[ColorType] = defaults.initial_color

  pixels: NeoPixel
  selected: dict[str, int|None]

  def __init__(self, pixels: NeoPixel) -> None:
    self.pixels = pixels
    self.selected = dict.fromkeys(('pixel', 'hue'))

  def deinit(self) -> None:
    for key in self.selected:
      self.selected[key] = None

  def pixel(self, verb: str, quantity: int|None) -> None:
    value = utils.resolve_index_change(verb, quantity, self.selected['pixel'], self.pixels.n, True)
    self.selected.update(pixel=value, hue=None)
    print(f'selected={self.selected}')

  def hue(self, verb: str, quantity: int|None) -> None:
    prange = self.prange()
    if self.selected['hue'] is None and quantity is not None:
      current = utils.unwheel(self.pixels[next(iter(prange))])
    else:
      current = self.selected['hue']
    value = utils.resolve_index_change(verb, quantity, current, 0x100, True)
    hue = utils.as_tuple(colorwheel(value or 0))
    for p in prange:
      self.pixels[p] = hue
    self.pixels.show()
    self.selected['hue'] = value
    print(f'selected={self.selected}')

  def brightness(self, verb: str, quantity: int|None) -> None:
    if verb == 'clear':
      value = self.initial_brightness
    elif verb == 'set':
      value = quantity
    elif verb == 'minus':
      value = math.ceil(self.pixels.brightness * self.brightness_scale) - quantity
    else:
      value = int(self.pixels.brightness * self.brightness_scale) + quantity
    value = max(0, min(self.brightness_scale, value)) / self.brightness_scale
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
      initial = utils.as_tuple(self.initial_color)
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

class Animator:

  speeds: ClassVar[Sequence[int]] = defaults.speeds
  routines: ClassVar[Sequence[str]] = (
    'anim_wheel_loop',
    'anim_buffers_loop',
    'anim_marquee_loop')

  pixels: NeoPixel
  bufstore: BufStore
  anim: Animation|None = None
  _speed: int
  
  def __init__(self, pixels: NeoPixel, bufstore: BufStore) -> None:
    self.pixels = pixels
    self.bufstore = bufstore
    self.speed = len(self.speeds) // 2

  @property
  def speed(self) -> int:
    return self._speed

  @speed.setter
  def speed(self, value: int) -> None:
    self._speed = max(0, min(value, len(self.speeds) - 1))
    if self.anim:
      self.anim.interval = self.speeds[self._speed]

  def deinit(self) -> None:
    self.clear()

  def run(self):
    if self.anim:
      try:
        self.anim.run()
      except StopIteration:
        self.clear()

  def speed_change(self, verb: str, quantity: int|None) -> None:
    self.speed = utils.resolve_index_change(
      verb,
      quantity,
      self.speed,
      len(self.speeds),
      False)

  def clear(self) -> None:
    self.anim = None

  def anim_wheel_loop(self) -> None:
    self.anim = FillAnimation(
      self.pixels,
      path=utils.repeat((0xff0000, 0xff00, 0xff)),
      interval=self.speeds[self.speed],
      steps=0x100)
    self.anim.start()

  def anim_buffers_loop(self) -> None:
    bufs = map(self.bufstore.read, self.bufstore.range)
    bufs = tuple(map(tuple, filter(None, bufs)))
    if len(bufs) < 2:
      raise ValueError('not enough buffers')
    self.anim = BufsAnimation(
      self.pixels,
      bufs=utils.repeat(bufs),
      interval=self.speeds[self.speed],
      steps=0x100)
    self.anim.start()

  def anim_marquee_loop(self) -> None:
    length = self.pixels.n
    if length < 2:
      raise ValueError('not enough pixels')
    rnge = range(length)
    buf = tuple(self.pixels)
    self.anim = BufsAnimation(
      self.pixels,
      bufs=(
        tuple(buf[n + p - length] for n in rnge)
        for p in utils.repeat(rnge)),
      interval=self.speeds[self.speed],
      steps=0x10)
    self.anim.start()

class BufStore:

  actions: ClassVar[Collection[str]] = 'restore', 'save', 'clear'
  fallback_color: ClassVar[ColorType] = defaults.initial_color

  subdir: str = 'buffers'

  def __init__(self, pixels: NeoPixel, sd: SdReader, size: int) -> None:
    self.pixels = pixels
    self.sd = sd
    self.size = size
    self.range = range(self.size)

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
    if index not in self.range:
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
    if index not in self.range:
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
    if index not in self.range:
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
    if index not in self.range:
      raise IndexError
    return f'{self.sd.path}/{self.subdir}/s{index:03}'

class SdReader:

  enabled: bool = True

  card: sdcardio.SDCard|None
  vfs: storage.VfsFat|None

  @property
  def checkfile(self) -> str:
    return f'{self.path}/.mountcheck'

  def __init__(self, spi: busio.SPI, cs: Pin, *, path: str = '/sd') -> None:
    self.spi = spi
    self.cs = cs
    self.path = path
    self.card = None
    self.vfs = None

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
      self.card = sdcardio.SDCard(self.spi, self.cs)
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
      raise ValueError(path)
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

  OFF: ClassVar[bool] = True
  ON: ClassVar[bool] = False

  io: DigitalInOut
  off_at: int|None = None

  def __init__(self, pin: Pin) -> None:
    self.io = DigitalInOut(pin)
    self.io.direction = Direction.OUTPUT
    self.io.value = self.OFF

  def deinit(self) -> None:
    self.io.deinit()

  def flash(self, duration: int = 0x80) -> None:
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
  pixels: NeoPixel
  interval: int
  at: int|None = None

  def start(self) -> None:
    self.at = ticks_ms()

  def ready(self) -> None:
    return self.at is not None and ticks_diff(ticks_ms(), self.at) >= 0

  def run(self) -> None:
    if self.ready():
      self.tick()
      self.at = ticks_add(ticks_ms(), self.interval)

  def tick(self) -> None:
    raise NotImplementedError

class FillAnimation(Animation):

  def __init__(self, pixels: NeoPixel, path: Iterable[ColorType], interval: int, steps: int) -> None:
    self.pixels = pixels
    self.it = utils.transitions(path, steps)
    self.interval = interval
    self.current = None

  def tick(self) -> None:
    value = next(self.it)
    if value != self.current:
      self.pixels.fill(value)
      self.pixels.show()
      self.current = value

class BufsAnimation(Animation):

  def __init__(self, pixels: NeoPixel, bufs: Iterable[Sequence[ColorType]], interval: int, steps: int) -> None:
    self.pixels = pixels
    self.its = tuple(
      utils.transitions(
        path=(buf[p] for buf in bufs),
        steps=steps)
      for p in range(self.pixels.n))
    self.bufs = bufs
    self.interval = interval

  def tick(self) -> None:
    change = False
    for p, it in enumerate(self.its):
      value = next(it)
      if change or self.pixels[p] != value:
        change = True
        self.pixels[p] = value
    if change:
      self.pixels.show()
