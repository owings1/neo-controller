from __future__ import annotations

try:
  from typing import Callable, Iterator
except ImportError:
  import defaults as _defaults
  import settings
  settings.__dict__.update(
    (name, getattr(settings, name, getattr(_defaults, name)))
    for name in _defaults.__dict__)
  del(_defaults)
else:
  import defaults as settings

from common import absindex as absindex
from common import Command
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms


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
