from __future__ import annotations

def resolve_index_change(verb: str, quantity: int|None, current: int|None, length: int, loop: bool) -> int|None:
  if verb == 'min':
    return 0
  if verb == 'max':
    return length - 1
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
    if loop:
      value = absindex(value, length)
    else:
      value = max(0, min(value, length - 1))
  return value

def as_tuple(value: ColorType) -> ColorTuple:
  if isinstance(value, tuple):
    return value
  r = value >> 0x10
  g = (value >> 0x8) & 0xff
  b = value & 0xff
  return r, g, b

def as_int(value: ColorType) -> int:
  if isinstance(value, int):
    return value
  r, g, b = value
  return (
    ((r & 0xff) << 0x10) +
    ((g & 0xff) << 0x8) +
    ((b & 0xff)))

def repeat(seq: Sequence[T]) -> Iterator[T]:
  while True:
    yield from seq

def transitions(path: Iterable[ColorType], steps: int) -> Iterator[ColorTuple]:
  for a, b in pairwise(path):
      yield from transition(a, b, steps)

def transition(a: ColorType, b: ColorType, steps: int) -> Iterator[ColorTuple]:
  if steps < 1:
    raise ValueError(steps)
  a = as_tuple(a)
  b = as_tuple(b)
  its = tuple(graduate(x, y, steps) for (x, y) in zip(a, b))
  for _ in range(steps):
    yield tuple(map(next, its))

def graduate(start: int, stop: int, steps: int) -> Iterator[int]:
  diff = stop - start
  for step in range(steps):
    yield round(start + step * (diff / steps))

def pairwise(it: Iterable[T]) -> Iterator[tuple[T, T]]:
  it = iter(it)
  try:
    a = next(it)
    while True:
      b = next(it)
      yield a, b
      a = b
  except StopIteration:
    pass

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

import defaults
import settings
settings = init_settings(defaults, settings)

# IDE Environment
try:
  from types import ModuleType
  from typing import Iterable, Iterator, Sequence, TypeAlias, TypeVar
  T = TypeVar('T')
  MT = TypeVar('MT', bound=ModuleType)
  ColorTuple: TypeAlias = tuple[int, int, int]
  ColorType: TypeAlias = int|ColorTuple
except ImportError:
  ColorTuple = tuple
  ColorType = tuple
