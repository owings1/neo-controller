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

def absindex(i: int, length: int) -> int:
  try:
    return i - (length * (i // length))
  except ZeroDivisionError:
    raise IndexError

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

def as_tuple(value: ColorType) -> tuple[int, int, int]:
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

def transitions(path: Iterable[ColorType], steps: int) -> Iterator[ColorTuple]:
  it = iter(path)
  a = next(it)
  b = next(it)
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
  for step in range(steps):
    yield transition_step(step, a, b, steps)
  # diffs = tuple(b - a for (a, b) in zip(a, b))
  # incs = tuple(diff / steps for diff in diffs)
  # yield a
  # for step in range(1, steps - 1):
  #   yield tuple(map(round, (a + inc * step for (a, inc) in zip(a, incs))))
  # yield b

def transition_step(step: int, a: ColorTuple, b: ColorTuple, steps: int) -> ColorTuple:
  return tuple(transition_increment(step, a, b, steps) for (a, b) in zip(a, b))

def transition_increment(step: int, x: int, y: int, steps: int) -> int:
  if step >= steps - 1:
    return y
  return round(x + ((y - x) / steps) * step)
