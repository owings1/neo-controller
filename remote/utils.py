from __future__ import annotations

import defaults
import settings
from common import absindex as absindex
from common import Command, init_settings
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms

settings = init_settings(defaults, settings)

class Repeater:

  func: Callable[[Command], None]
  at: int|None = None
  cmd: Command|None = None
  threshold: int = settings.repeat_threshold
  interval: int = settings.repeat_interval

  def __init__(self, func: Callable) -> None:
    self.func = func
  def deinit(self) -> None:
    self.at = None

  def clear(self) -> None:
    self.at = None
    self.cmd = None

  def schedule(self, cmd: Command) -> None:
    self.cmd = cmd
    self.at = ticks_add(ticks_ms(), self.threshold)

  def run(self) -> None:
    if self.ready():
      self.tick()

  def tick(self) -> None:
    self.at = ticks_add(self.at, self.interval)
    self.func(self.cmd)

  def ready(self) -> bool:
    return self.at is not None and ticks_diff(ticks_ms(), self.at) >= 0

def cmdid_gen() -> Iterator[str]:
  ranges = tuple(
    range(ord(x), ord(y) + 1)
    for x, y in ('09', 'az', 'AZ'))
  while True:
    for r in ranges:
      yield from map(chr, r)

# IDE Environment
try:
  from typing import Callable, Iterator
except ImportError:
  pass
