from __future__ import annotations

try:
  from typing import Iterable, Iterator, Sequence, TypeAlias, TypeVar
  T = TypeVar('T')
  ColorTuple: TypeAlias = tuple[int, int, int]
  ColorType: TypeAlias = int|ColorTuple
except ImportError:
  ColorType = ColorTuple = tuple
  import defaults as _defaults
  import settings
  settings.__dict__.update(
    (name, getattr(settings, name, getattr(_defaults, name)))
    for name in _defaults.__dict__)
  del(_defaults)
else:
  import defaults as settings

from common import absindex

def resolve_index_change(verb: str, quantity: int|None, current: int|None, length: int, loop: bool) -> int|None:
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
  r = value >> 16
  g = (value >> 8) & 0xff
  b = value & 0xff
  return r, g, b

def as_int(value: ColorType) -> int:
  if isinstance(value, int):
    return value
  r, g, b = value
  return (
    ((r & 0xff) << 16) +
    ((g & 0xff) << 8) +
    ((b & 0xff)))

def unwheel(value: ColorType) -> int:
  rgb = list(as_tuple(value))
  if all(rgb):
    rgb[rgb.index(min(rgb))] = 0
  total = sum(rgb)
  correct = 0xff - total
  if correct:
    for i in range(3):
      rgb[i] += int(correct * (rgb[i] / 0xff))
    total = sum(rgb)
    correct = 0xff - total
    if correct:
      for i in range(3):
        if rgb[i] and 0 <= rgb[i] + correct <= 0xff:
          rgb[i] += correct
          break
      total = sum(rgb)
  if total != 0xff:
    return 0
  if not rgb[2]:
    return rgb[1] // 3
  if not rgb[0]:
    return rgb[2] // 3 + 85
  return rgb[0] // 3 + 170

def repeat(seq: Sequence[T]) -> Iterator[T]:
  while True:
    yield from seq

def buffer_transitions(bufs: Iterable[Sequence[ColorType]], steps: int) -> Iterator[Sequence[ColorTuple]]:
  it = iter(bufs)
  try:
    b1 = next(it)
    b2 = next(it)
  except StopIteration:
    return
  P = range(len(b1))
  S = range(steps)
  while True:
    its = tuple(transition(b1[p], b2[p], steps) for p in P)
    for _ in S:
      yield tuple(map(next, its))
    try:
      b1, b2 = b2, next(it)
    except StopIteration:
      break

def transitions(path: Iterable[ColorType], steps: int) -> Iterator[ColorTuple]:
  it = iter(path)
  try:
    a = next(it)
    b = next(it)
  except StopIteration:
    return
  while True:
    yield from transition(a, b, steps)
    try:
      a, b = b, next(it)
    except StopIteration:
      break

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
  yield start
  for step in range(1, steps - 1):
    yield round(start + step * (diff / steps))
  yield stop
