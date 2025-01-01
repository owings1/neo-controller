from __future__ import annotations

from collections import namedtuple

from adafruit_ticks import ticks_add, ticks_diff, ticks_ms
from digitalio import DigitalInOut, Direction
from microcontroller import Pin

class Command(namedtuple('Command', ('what', 'verb', 'quantity'))):
  what: str
  verb: str
  quantity: int|None

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

  def set(self, on: bool) -> None:
    self.io.value = self.ON if on else self.OFF

  def on(self) -> None:
    self.set(True)

  def off(self) -> None:
    self.set(False)

  def flash(self, duration: int = 0x80) -> None:
    self.io.value = self.ON
    self.off_at = ticks_add(ticks_ms(), duration)

  def run(self) -> None:
    if self.off_at is not None and self.io.value is self.ON:
      if ticks_diff(ticks_ms(), self.off_at) >= 0:
        self.io.value = self.OFF
        self.off_at = None

def absindex(i: int, length: int) -> int:
  try:
    return i - (length * (i // length))
  except ZeroDivisionError:
    raise IndexError

def init_settings(defaults: MT, settings: ModuleType) -> MT:
  for name in defaults.__dict__:
    if not hasattr(settings, name):
      setattr(settings, name, getattr(defaults, name))
  return settings

# IDE Environment
try:
  from types import ModuleType
  from typing import ClassVar, TypeVar
  MT = TypeVar('MT', bound=ModuleType)
except ImportError:
  pass
