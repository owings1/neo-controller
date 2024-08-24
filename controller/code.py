from __future__ import annotations

from defaults import *

try:
  from settings import *
except ImportError as e:
  print(f'Error loading settings: {type(e).__name__}: {e}')

from terms import *

import time

import busio
import board 
import neopixel

pixels: neopixel.NeoPixel|None = None
serial: busio.UART|None = None

def init():
  pixels.fill(0x100000)
  pixels.show()

def loop():
  cmdstr = serial.readline()
  if cmdstr:
    cmdstr = cmdstr.decode().strip('\x00').strip()
  if not cmdstr:
    return
  print(f'{cmdstr=}')
  try:
    cmd = parse_command(cmdstr)
  except (ValueError, KeyError) as err:
    print(f'Warning: {type(err)}: {err}')
    return
  print(f'{cmd=}')
  do_command(cmd)

def parse_command(cmdstr: str):
  verb, key = cmdstr[:2]
  if len(cmdstr) > 2:
    if cmdstr[2] != ' ':
      raise ValueError(f'Unexpected separator {cmdstr[3]}')
    quantity = float(cmdstr[3:])
  else:
    quantity = None
  return verb, key, quantity

def do_command(cmd: tuple[str, str, float|None]):
  verb, key, quantity = cmd
  if verb == VERB_SELECT:
    do_select(key, quantity)
  elif verb == VERB_ADJUST:
    do_adjust(key, quantity)
  else:
    raise ValueError(f'{verb=}')

def do_select(key: str, quantity: int|None):
  if quantity is None:
    selected[key] = None
    return
  if quantity != int(quantity):
    raise ValueError(f'{quantity=}')
  if not quantity:
    return
  if selected[key] is None:
    selected[key] = 0
    if quantity > 0:
      quantity -= 1
  selected[key] += quantity
  while selected[key] > limits[key]:
    selected[key] -= limits[key]
  while selected[key] < 0:
    selected[key] += limits[key]

def do_adjust(key: str, quantity: float|None):
  if key == KEY_BRIGHTNESS:
    value = pixels.brightness + quantity
    pixels.brightness = max(0, min(1, value))
    pixels.show()
    return
  if key != KEY_INTENSITY:
    raise ValueError(f'{key=}')
  if quantity is not None and quantity != int(quantity):
    raise ValueError(f'{quantity=}')
  if selected[KEY_PIXEL] is None:
    prange = range(num_pixels)
  else:
    prange = (selected[KEY_PIXEL],)
  if selected[KEY_BIT] is None:
    brange = range(len(pixel_order))
  else:
    brange = (selected[KEY_BIT],)
  for p in prange:
    values = list(pixels[p])
    for b in brange:
      if quantity is None:
        values[b] = 0
      else:
        values[b] = min(16, max(0, values[b] + quantity))
    pixels[p] = tuple(values)
  pixels.show()
  print(pixels)

selected = {
  KEY_BIT: None,
  KEY_PIXEL: None,
}

limits = {
  KEY_BIT: len(pixel_order) - 1,
  KEY_PIXEL: num_pixels,
}


try:
  serial = busio.UART(
    None,
    board.RX,
    baudrate=baudrate,
    timeout=0.1)
  pixels = neopixel.NeoPixel(
      getattr(board, data_pin),
      num_pixels,
      brightness=1,
      auto_write=False,
      pixel_order=pixel_order)
  init()
  while True:
    loop()
finally:
  if serial:
    serial.deinit()
  if pixels:
    pixels.deinit()
