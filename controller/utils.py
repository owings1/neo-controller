from __future__ import annotations

try:
  from typing import Sequence, TypeAlias
  ColorType: TypeAlias = int|tuple[int, int, int]
except ImportError:
  ColorType = tuple
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

def transitions(path: Sequence[ColorType], steps: int, loop: bool = False):
  if len(path) < 2:
    raise ValueError(path)
  while True:
    it = iter(path)
    a = next(it)
    while True:
      try:
        b = next(it)
      except StopIteration:
        break
      yield from transition(a, b, steps)
      a = b
    if not loop:
      break
    b = next(iter(path))
    yield from transition(a, b, steps)

def transition(a: ColorType, b: ColorType, steps: int):
  if steps < 1:
    raise ValueError(steps)
  a = as_tuple(a)
  b = as_tuple(b)
  diffs = tuple(b - a for (a, b) in zip(a, b))
  incs = tuple(diff / steps for diff in diffs)
  yield a
  for step in range(1, steps - 1):
    yield tuple(map(round, (a + inc * step for (a, inc) in zip(a, incs))))
  yield b
