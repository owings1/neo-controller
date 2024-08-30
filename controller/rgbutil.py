from __future__ import annotations

try:
  from typing import Sequence
except ImportError:
  pass

def as_tuple(value: int|tuple) -> tuple[int, int, int]:
  if isinstance(value, tuple):
    return value
  r = value >> 16
  g = (value >> 8) & 0xff
  b = value & 0xff
  return r, g, b

def as_int(value: int|tuple[int, int, int]) -> int:
  if isinstance(value, int):
    return value
  r, g, b = value
  return (
    ((r & 0xff) << 16) +
    ((g & 0xff) << 8) +
    ((b & 0xff)))

def wheel_reverse(*rgb: int) -> int:
  rgb = list(rgb)
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

def transitions(path: Sequence[int|tuple[int, int, int]], steps: int, loop: bool = False):
  if len(path) < 2:
    raise ValueError(path)
  path = tuple(map(as_tuple, path))
  while True:
    trail = iter(path)
    start = next(trail)
    while True:
      try:
        end = next(trail)
      except StopIteration:
        break
      yield from transition(start, end, steps)
      start = end
    if not loop:
      break
    end = next(iter(path))
    yield from transition(start, end, steps)

def transition(start: int|tuple[int, int, int], end: int|tuple[int, int, int], steps: int):
  if steps < 1:
    raise ValueError(steps)
  start = as_tuple(start)
  end = as_tuple(end)
  # print(f'{start=} {end=}')
  diffs = tuple(b - a for (a, b) in zip(start, end))
  incs = tuple(diff / steps for diff in diffs)
  yield start
  for step in range(1, steps - 1):
    yield tuple(map(round, (a + inc * step for (a, inc) in zip(start, incs))))
  yield end
