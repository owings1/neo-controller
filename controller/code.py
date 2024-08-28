from __future__ import annotations

from defaults import *

try:
  from settings import *
except ImportError as e:
  print(f'Error loading settings: {type(e).__name__}: {e}')

from terms import *

try:
  from typing import Any, Collection, Iterable, Iterator
except ImportError:
  pass

import traceback

import board
import busio
import neopixel
import sdcardio
import storage
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms
from digitalio import DigitalInOut, Direction
from microcontroller import Pin

OFF, ON = OFFON = True, False

pixels: neopixel.NeoPixel|None = None
serial: busio.UART|None = None
actled: DigitalInOut|None = None
selected: dict[str, Any] = {}
offat: dict[DigitalInOut, int] = {}
sd: sdcardio.SDCard|None = None
vfs: storage.VfsFat|None = None
color_to_indexes: dict[str, Collection[int]] = {
  'red': (0,),
  'green': (1,),
  'blue': (2,),
  'white': ...,
}

def main() -> None:
  try:
    init()
    while True:
      loop()
  finally:
    deinit()

def init() -> None:
  global actled, pixels, serial
  serial = busio.UART(
    board.TX,
    board.RX,
    baudrate=baudrate,
    timeout=0.1)
  pixels = neopixel.NeoPixel(
      getattr(board, data_pin),
      num_pixels,
      auto_write=False,
      pixel_order=pixel_order)
  color_to_indexes['white'] = (
    (3,) if pixels.bpp > 3
    else range(pixels.bpp))
  actled = init_led(board.LED_GREEN)
  init_sdcard()
  if not do_state_restore():
    pixels.fill(initial_color)
    pixels.brightness = initial_brightness / 16
    pixels.show()
  selected['pixel'] = None

def deinit() -> None:
  if serial:
    serial.deinit()
  if pixels:
    pixels.deinit()
  if actled:
    actled.deinit()
  deinit_sdcard()

def loop() -> None:
  cmdstr = read_cmdstr()
  if not cmdstr:
    flash_check()
    return
  flash(actled)
  print(f'{cmdstr=}')
  try:
    cmd = parse_command(cmdstr)
    print(f'{cmd=}')
    do_command(*cmd)
  except Exception as err:
    print(f'Warning: {type(err)}: {err}')

def read_cmdstr() -> str|None:
  serial.read()
  cmdstr = serial.readline()
  if cmdstr:
      cmdstr = str(cmdstr, 'utf-8')
      cmdstr = cmdstr.strip('\x00').strip()
  return cmdstr or None

def parse_command(cmdstr: str) -> tuple[str, str, int|None]:
  what, verb = actions[cmdstr[0]]
  if len(cmdstr) == 1 or verb == 'clear':
    quantity = None
  else:
    quantity = int(cmdstr[1:])
  return what, verb, quantity

def do_command(what: str, verb: str, quantity: int|None) -> None:
  action = (what, verb)
  if action not in codes:
    raise ValueError(action)
  if what == 'func':
    if verb == 'draw':
      pixels.show()
    elif verb == 'save':
      do_state_save(quantity)
    elif verb == 'restore':
      do_state_restore(quantity)
    else:
      raise ValueError(verb)
  elif what == 'pixel':
    do_pixel_select(verb, quantity)
  elif what == 'hue':
    do_hue_change(verb, quantity)
  elif what == 'brightness':
    do_brightness_change(verb, quantity)
  elif what in color_to_indexes:
    do_color_change(what, verb, quantity)
  else:
    raise ValueError(what)

def do_pixel_select(verb: str, quantity: int|None) -> None:
  if verb == 'clear' or quantity is None:
    value = None
  else:
    if verb == 'set':
      if quantity < 0:
        quantity += num_pixels
      if 0 <= quantity < num_pixels:
        value = quantity
      else:
        raise IndexError(quantity)
    else:
      value = selected['pixel']
      if verb == 'minus':
        quantity *= -1
      if value is None:
        value = 0
        if quantity > 0:
          quantity -= 1
      value += quantity
      value -= num_pixels * (value // num_pixels)
  selected['pixel'] = value
  print(f'{selected=}')

def do_brightness_change(verb: str, quantity: int|None) -> None:
  if verb == 'clear' or quantity is None:
    value = initial_brightness
  else:
    if verb == 'set':
      value = quantity
    else:
      value = int(pixels.brightness * 16)
      if verb == 'minus':
        quantity *= -1
      value += quantity
  value = max(0, min(16, value)) / 16
  change = value != pixels.brightness
  print(f'brightness={pixels.brightness} {change=}')
  if change:
    pixels.brightness = value
    pixels.show()

def do_hue_change(verb: str, quantity: int|None) -> None:
  ...
def do_color_change(color: str, verb: str, quantity: int|None) -> None:
  indexes = color_to_indexes[color]
  if selected['pixel'] is None:
    prange = range(num_pixels)
  else:
    prange = (selected['pixel'],)
  if quantity is not None:
    if verb == 'minus':
      quantity *= -1
  change = False
  for p in prange:
    values = list(pixels[p])
    pchange = False
    for b in indexes:
      if verb == 'clear' or quantity is None:
        value = initial_color[b]
      elif verb == 'set':
        value = quantity
      else:
        value = values[b] + quantity
      value = max(0, min(16, value))
      pchange |= values[b] != value
      values[b] = value
    if pchange:
      pixels[p] = tuple(values)
      change = True
      print(f'{p=} {pixels[p]}')
  if change:
    pixels.show()

def do_state_save(index: int|None = None) -> bool:
  if not (sd_enabled and check_init_sdcard()):
    return False
  name = 'state'
  if index is not None:
    name = f'{name}_{index}'
  text = '\n'.join(state_pack())
  try:
    with open(f'/sd/{name}', 'w') as file:
      file.write(text)
  except OSError as err:
    traceback.print_exception(err)
    return False
  return True

def do_state_restore(index: int|None = None) -> bool:
  state = state_read(index)
  if not state:
    return False
  brightness, values = state
  pixels.brightness = brightness / 16
  for p, value in enumerate(values):
    pixels[p] = value
  pixels.show()
  return True

def state_read(index: int|None = None) -> tuple[int, tuple[int, ...]]|None:
  if not (sd_enabled and check_init_sdcard()):
    return
  name = 'state'
  if index is not None:
    name = f'{name}_{index}'
  try:
    with open(f'/sd/{name}') as file:
      text = file.read().strip()
  except OSError as err:
    traceback.print_exception(err)
    return
  try:
    brightness, *values = state_unpack(text.splitlines())
  except ValueError as err:
    traceback.print_exception(err)
    return
  return brightness, values

def state_pack() -> Iterator[str]:
  yield str(int(pixels.brightness * 16))
  for value in pixels:
    yield ','.join(map(str, value))

def state_unpack(packed: Iterable[str]):
  it = iter(packed)
  try:
    yield int(next(it))
  except StopIteration:
    raise ValueError
  for i, line in enumerate(it):
    if i >= num_pixels:
      break
    value = tuple(map(int, line.split(',')))
    if len(value) > pixels.bpp:
      value = value[:pixels.bpp]
    elif len(value) != pixels.bpp:
      raise ValueError(value)
    yield value

def init_led(pin: Pin) -> DigitalInOut:
  led = DigitalInOut(pin)
  led.direction = Direction.OUTPUT
  led.value = OFF
  return led

def flash(io: DigitalInOut, ms: int = 100) -> None:
  io.value = ON
  offat[io] = ticks_add(ticks_ms(), ms)

def flash_check() -> None:
  for io in offat:
    if io.value is ON and ticks_diff(ticks_ms(), offat[io]) >= 0:
      io.value = OFF

def check_init_sdcard() -> bool:
  if sd:
    try:
      open('/sd/.mountcheck').close()
      return True
    except OSError:
      pass
  return init_sdcard()

def init_sdcard() -> bool:
  if not sd_enabled:
    return False
  global sd
  deinit_sdcard()
  try:
    sd = sdcardio.SDCard(board.SPI(), getattr(board, sd_cs_pin))
    storage.mount(storage.VfsFat(sd), '/sd')
    open('/sd/.mountcheck', 'w').close()
  except OSError as err:
    traceback.print_exception(err)
    deinit_sdcard()
    return False
  return True

def deinit_sdcard() -> None:
  global sd
  if sd:
    try:
      storage.umount('/sd')
    except OSError:
      pass
    sd.deinit()
    sd = None

if __name__ == '__main__':
  main()
