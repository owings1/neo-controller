from __future__ import annotations

def absindex(i: int, length: int) -> int:
  try:
    return i - (length * (i // length))
  except ZeroDivisionError:
    raise IndexError
