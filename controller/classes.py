from __future__ import annotations

import math
import os
import traceback
from collections import namedtuple

import busio
import sdcardio
import storage
import utils
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms
from microcontroller import Pin
from neopixel import NeoPixel
from rainbowio import colorwheel
from utils import ColorType, settings

import terms
from common import Command, Led

try:
  from typing import (Any, ClassVar, Collection, Iterable, Iterator, Self,
                      Sequence)
except ImportError:
  pass

__all__ = (
  'ActLeds',
  'Animator',
  'BufStore',
  'Changer',
  'Command',
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
    cmdstr = cmdstr[1:]
    self.lastid = cmdid
    return cmdstr or None

  def parse(self, cmdstr: str) -> Command:
    what, verb = terms.ACTIONS[cmdstr[0]]
    if len(cmdstr) == 1:
      quantity = None
    else:
      if what == 'buffer' and verb == 'set':
        quantity = tuple(map(int, cmdstr[1:].split(',')))
      else:
        quantity = int(cmdstr[1:])
    return Command(what, verb, quantity)

class Changer:
  whats: ClassVar[Collection[str]] = (
    'buffer',
    'color',
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

  def buffer(self, verb: str, buf: Sequence[ColorType]) -> None:
    if verb != 'set':
      raise ValueError(verb)
    change = False
    for p in range(self.pixels.n):
      try:
        value = utils.as_int(buf[p])
      except IndexError:
        break
      cur = utils.as_int(self.pixels[p])
      if cur != value:
        self.pixels[p] = value
        change = True
    if change:
      self.pixels.show()
    print(f'buffer={buf}')

  def color(self, verb: str, value: ColorType|int) -> None:
    if verb == 'set':
      value = min(0xffffff, max(0, utils.as_int(value)))
    elif verb == 'copy':
      value = utils.as_int(self.pixels[utils.absindex(value, self.pixels.n)])
    else:
      raise ValueError(verb)
    change = False
    for p in self.prange():
      cur = utils.as_int(self.pixels[p])
      if cur != value:
        self.pixels[p] = value
        change = True
    if change:
      self.pixels.show()
    print(f'color={value}')

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

  def shade(color: str, indexes: Collection[int]):
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

  red = shade('red', (0,))
  green = shade('green', (1,))
  blue = shade('blue', (2,))
  white = shade('white', range(3))

  del(shade)

  def prange(self) -> Collection[int]:
    if self.selected['pixel'] is None:
      return range(self.pixels.n)
    return (self.selected['pixel'],)

class Animator:
  routines: ClassVar[Sequence[str]] = (
    'anim_wheel_loop',
    'anim_buffers_loop',
    'anim_marquee_loop')
  pixels: NeoPixel
  bufstore: BufStore
  anim: Animation|None = None
  custom: Any = None
  _speed: int
  
  def __init__(self, pixels: NeoPixel, bufstore: BufStore, custom: Any = None) -> None:
    self.pixels = pixels
    self.bufstore = bufstore
    self.speed = len(settings.speeds) // 2
    self.custom = custom

  @property
  def speed(self) -> int:
    return self._speed

  @speed.setter
  def speed(self, value: int) -> None:
    self._speed = max(0, min(value, len(settings.speeds) - 1))
    if self.anim:
      self.anim.interval = settings.speeds[self._speed]

  def deinit(self) -> None:
    self.clear()

  def run(self):
    if self.anim:
      try:
        self.anim.run()
      except StopIteration:
        self.clear()

  def speed_change(self, verb: str, quantity: int|None) -> None:
    if quantity is None:
      self.speed = len(settings.speeds) // 2
      return
    quantity *= -1
    self.speed = utils.resolve_index_change(
      verb,
      quantity,
      self.speed,
      len(settings.speeds),
      False)

  def clear(self) -> None:
    self.anim = None

  def anim_wheel_loop(self) -> None:
    self.anim = FillAnimation(
      self.pixels,
      path=(0xff0000, 0xff00, 0xff),
      interval=settings.speeds[self.speed],
      steps=0x100)
    self.anim.start()

  def anim_buffers_loop(self) -> None:
    if self.custom and (func := getattr(self.custom, 'buffers_loop', None)):
      print(f'Running custom.buffers_loop')
      self.anim = BufiterAnimation(
        self.pixels,
        it=func(len(self.pixels)),
        interval=settings.speeds[self.speed],
        steps=0x50)
    else:
      print(f'Running bufstore animation')
      self.anim = BufstoreAnimation(
        self.pixels,
        store=self.bufstore,
        interval=settings.speeds[self.speed],
        steps=0x50)
    self.anim.start()

  def anim_marquee_loop(self) -> None:
    self.anim = MarqueeAnimation(
      self.pixels,
      interval=settings.speeds[self.speed],
      steps=0x20)
    self.anim.start()

class BufStore:
  actions: ClassVar[Collection[str]] = 'restore', 'save', 'clear'

  def __init__(self, pixels: NeoPixel, sd: SdReader, subdir: str, size: int) -> None:
    self.pixels = pixels
    self.sd = sd
    self.subdir = subdir.strip('/')
    self.size = size
    self.range = range(self.size)
    self.onreadstart = None
    self.onreadstop = None

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
      print(f'Did not read buf {index=} filling with {settings.initial_color}')
      self.pixels.fill(settings.initial_color)
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
        if isinstance(err, OSError) and err.errno == 2:
          print(f'buf {index} not found')
        else:
          traceback.print_exception(err)
      else:
        return True
    return False

  def read(self, index: int) -> Iterator[int]|None:
    if self.pixels.n > 0 and self.has(index):
        return self._reader(self.file(index), self.pixels.n)

  def _reader(self, file: str, stop: int) -> Iterator[int]:
    i = 0
    if self.onreadstart:
      self.onreadstart()
    try:
      with open(file) as f:
        while True:
          line = f.readline()
          while line:
            line = line.strip()
            if line:
              try:
                value = int(line)
              except ValueError as err:
                traceback.print_exception(err)
              else:
                yield value
                i += 1
                if i == stop:
                  break
            line = f.readline()
          if i == 0:
            # empty file
            break
          if i == stop:
            break
          f.seek(0)
    finally:
      if self.onreadstop:
        self.onreadstop()

  def file(self, index: int) -> str:
    if index not in self.range:
      raise IndexError
    return f'{self.sd.path}/{self.subdir}/s{index:03}'

class SdReader:
  card: sdcardio.SDCard|None = None
  vfs: storage.VfsFat|None = None

  @property
  def checkfile(self) -> str:
    return f'{self.path}/.mountcheck'

  def __init__(self, spi: busio.SPI, cs: Pin, *, path: str = '/sd') -> None:
    self.spi = spi
    self.cs = cs
    self.path = path

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
    if not settings.sd_enabled:
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
  it: Iterable[Sequence[ColorType]]

  def start(self) -> None:
    self.at = ticks_ms()

  def ready(self) -> None:
    return self.at is not None and ticks_diff(ticks_ms(), self.at) >= 0

  def run(self) -> None:
    if self.ready():
      self.tick()
      self.at = ticks_add(ticks_ms(), self.interval)

  def tick(self) -> None:
    change = False
    for p, value in enumerate(next(self.it)):
      if change or self.pixels[p] != utils.as_tuple(value):
        change = True
        self.pixels[p] = value
    if change:
      self.pixels.show()   

class FillAnimation(Animation):
  'Transition through single solid colors'

  def __init__(self, pixels: NeoPixel, path: Iterable[ColorType], interval: int, steps: int) -> None:
    self.pixels = pixels
    self.interval = interval
    r = range(len(self.pixels))
    self.it = ((x for _ in r) for x in utils.transitions(utils.repeat(path), steps))

class BufstoreAnimation(Animation):
  'Transition through buffers from a buffer store'

  def __init__(self, pixels: NeoPixel, store: BufStore, interval: int, steps: int) -> None:
    self.pixels = pixels
    self.interval = interval
    self.it = utils.buffer_transitions(self.readrepeat(store), steps)

  @classmethod
  def readrepeat(self, store: BufStore) -> Iterator[Sequence[ColorType]]:
    i = 0
    while True:
      # Scan for next distinct readable buffer
      for _ in range(store.size - 1):
        reader = store.read(i)
        i = utils.absindex(i + 1, store.size)
        if reader:
          yield tuple(reader)
          break
      else:
        break

class MarqueeAnimation(Animation):
  'Pixel shift transition'

  def __init__(self, pixels: NeoPixel, interval: int, steps: int) -> None:
    self.pixels = pixels
    self.interval = interval
    buf = tuple(self.pixels)
    L = len(buf)
    self.its = tuple(
      utils.transitions(path, steps)
      for path in (
        (buf[utils.absindex(i, L)] for i in utils.repeat(r))
        for r in (range(n, L + n)
          for n in range(L))))
    self.it = (map(next, self.its) for _ in utils.repeat('_'))

class BufiterAnimation(Animation):
  'Custom buffer iterator'

  def __init__(self, pixels: NeoPixel, it: Iterable[Sequence[ColorType]], interval: int, steps: int) -> None:
    self.pixels = pixels
    self.interval = interval
    self.it = utils.buffer_transitions(it, steps)
