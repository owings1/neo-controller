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
from rainbowio import colorwheel

OFF, ON = OFFON = True, False

brightness_scale = 100
lastid: str|None = None
pixels: neopixel.NeoPixel|None = None
serial: busio.UART|None = None
actled: DigitalInOut|None = None
errled: DigitalInOut|None = None
selected: dict[str, Any] = {}
offat: dict[DigitalInOut, int] = {}
sd: sdcardio.SDCard|None = None
color_to_indexes: dict[str, Collection[int]] = {
  'red': (0,),
  'green': (1,),
  'blue': (2,),
  'white': range(3),
}

def main() -> None:
  try:
    init()
    while True:
      loop()
  finally:
    deinit()

def init() -> None:
  global actled, errled, lastid, pixels, serial
  serial = busio.UART(
    None,
    board.RX,
    baudrate=baudrate,
    timeout=serial_timeout)
  pixels = neopixel.NeoPixel(
      getattr(board, data_pin),
      num_pixels,
      auto_write=False,
      pixel_order=pixel_order)
  actled = init_led(board.LED_GREEN)
  errled = init_led(board.LED_BLUE)
  init_sdcard()
  do_state_restore()
  selected['pixel'] = None
  selected['hue'] = None
  lastid = None

def deinit() -> None:
  if serial:
    serial.deinit()
  if pixels:
    pixels.deinit()
  if actled:
    actled.deinit()
  if errled:
    errled.deinit()
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
    traceback.print_exception(err)
    flash(errled)

def read_cmdstr() -> str|None:
  global lastid
  cmdstr = serial.readline()
  if cmdstr:
      cmdstr = cmdstr.strip(b'\x00')
      try:
        cmdstr = str(cmdstr, 'utf-8').strip()
      except UnicodeError as err:
        traceback.print_exception(err)
        cmdstr = None
      if cmdstr:
        if cmdstr[0] == lastid:
          cmdstr = None
        else:
          lastid = cmdstr[0]
          cmdstr = cmdstr[1:]
      else:
        flash(errled)
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
    elif verb == 'run':
      do_run(quantity)
    elif verb == 'noop':
      pass
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
  value = resolve_index_change(verb, quantity, selected['pixel'], num_pixels)
  selected['pixel'] = value
  selected['hue'] = None
  print(f'{selected=}')

def do_hue_change(verb: str, quantity: int|None) -> None:
  value = resolve_index_change(verb, quantity, selected['hue'], 0x100)
  hue = as_tuple(
    0xffffff if value is None
    else colorwheel(value))
  if selected['pixel'] is None:
    prange = range(num_pixels)
  else:
    prange = (selected['pixel'],)
  for p in prange:
    pixels[p] = hue
  pixels.show()
  selected['hue'] = value
  print(f'{selected=}')

def do_brightness_change(verb: str, quantity: int|None) -> None:
  if verb == 'clear' or quantity is None:
    value = initial_brightness
  else:
    if verb == 'set':
      value = quantity
    else:
      value = int(pixels.brightness * brightness_scale)
      if verb == 'minus':
        quantity *= -1
      value += quantity
  value = max(0, min(brightness_scale, value)) / brightness_scale
  change = value != pixels.brightness
  print(f'brightness={pixels.brightness} {change=}')
  if change:
    pixels.brightness = value
    pixels.show()

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
  initial = as_tuple(initial_color)
  for p in prange:
    values = list(pixels[p])
    pchange = False
    for b in indexes:
      if verb == 'clear' or quantity is None:
        value = initial[b]
      elif verb == 'set':
        value = quantity
      else:
        value = values[b] + quantity
      value = max(0, min(0xff, value))
      pchange |= values[b] != value
      values[b] = value
    if pchange:
      pixels[p] = tuple(values)
      change = True
      print(f'{p=} {pixels[p]}')
  if change:
    pixels.show()
  selected['hue'] = None

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
  selected['hue'] = None
  state = state_read(index)
  if not state:
    pixels.brightness = initial_brightness / brightness_scale
    pixels.fill(initial_color)
    pixels.show()
    return False
  brightness, values = state
  pixels.brightness = brightness / brightness_scale
  length = len(values)
  change = False
  for p in range(num_pixels):
    value = values[absindex(p, length)]
    if change or pixels[p] != value:
      change = True
      pixels[p] = value
  if change:
    pixels.show()
  return True

def do_run(index: int|None = None):
  ...

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
  yield str(int(pixels.brightness * brightness_scale))
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
    if len(value) == 1:
      value = as_tuple(value[0])
    if len(value) != pixels.bpp:
      raise ValueError(value)
    yield value

def resolve_index_change(verb: str, quantity: int|None, current: int|None, length: int) -> int|None:
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
    value = absindex(value, length)
  return value

def as_tuple(value: int|tuple) -> tuple[int, int, int]:
  if isinstance(value, tuple):
    return value
  r = value >> 16
  g = (value >> 8) & 0xff
  b = value & 0xff
  return r, g, b

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

def absindex(i: int, length: int) -> int:
  try:
    return i - (length * (i // length))
  except ZeroDivisionError:
    raise IndexError

if __name__ == '__main__':
  main()
