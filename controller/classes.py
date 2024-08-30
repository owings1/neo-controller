from __future__ import annotations

import traceback

try:
  from typing import Iterable, Iterator, TypeAlias
except ImportError:
  ColorType = tuple
else:
  ColorType: TypeAlias = int|tuple[int, int, int]
import os
from collections import namedtuple

import board
import rgbutil
import sdcardio
import storage
import utils
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms
from digitalio import DigitalInOut, Direction
from microcontroller import Pin
from neopixel import NeoPixel

class StateManager:

  actions = 'restore', 'save', 'clear'

  subdir: str = 'states'
  fallback_color: ColorType = 0xffffff

  def __init__(self, pixels: NeoPixel, sd: SdReader) -> None:
    self.pixels = pixels
    self.sd = sd

  def deinit(self) -> None:
    pass

  def action(self, verb: str, index: int) -> bool:
    if verb in self.actions:
      func = getattr(self, verb)
    else:
      raise ValueError(verb)
    return bool(func(index))

  def restore(self, index: int) -> bool:
    values = self.read(index)
    if not values:
      self.pixels.fill(self.fallback_color)
      self.pixels.show()
      return False
    change = False
    srcstop = None
    it = iter(values)
    for p in range(self.pixels.n):
      if srcstop is None:
        try:
          value = next(it)
        except StopIteration:
          srcstop = p
      if srcstop is not None:
        if srcstop == 0:
          # Edge case of empty values
          value = self.fallback_color
        else:
          # Use relative index already written
          value = self.pixels[utils.absindex(p, srcstop)]
      if change or self.pixels[p] != value:
        change = True
        self.pixels[p] = value
    if change:
      self.pixels.show()
    return True

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

  def clear(self, index: int) -> bool:
    if not self.sd.checkmount():
      return False
    try:
      os.remove(self.file(index))
    except OSError as err:
      if err.errno != 2:
        traceback.print_exception(err)
        return False
    return True

  def read(self, index: int) -> Iterator[ColorType]|None:
    if self.sd.checkmount():
      try:
        with open(self.file(index)) as file:
          text = file.read().strip()
        return self.unpack(text.splitlines())
      except (OSError, ValueError) as err:
        traceback.print_exception(err)

  def pack(self) -> Iterator[str]:
    return map(hex, map(rgbutil.as_int, self.pixels))

  def unpack(self, packed: Iterable[str]) -> Iterator[ColorType]:
    for i, line in enumerate(packed):
      if i >= self.pixels.n:
        break
      if line.startswith('0x'):
        value = rgbutil.as_tuple(int(line))
      else:
        value = tuple(map(int, line.split(',', 2)))
      yield value

  def file(self, index: int) -> str:
    return f'{self.sd.path}/{self.subdir}/s{index:03}'

class SdReader:

  card: sdcardio.SDCard|None
  vfs: storage.VfsFat|None

  @property
  def checkfile(self) -> str:
    return f'{self.path}/.mountcheck'

  def __init__(self, cs: Pin, *, path: str = '/sd',) -> None:
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

  def run(self):
    for led in self:
      led.run()

  def deinit(self):
    for led in self:
      led.deinit()

  @staticmethod
  def frompins(*pins) -> ActLeds:
    return ActLeds(*map(Led, pins))
