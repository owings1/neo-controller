from __future__ import annotations

from defaults import *

try:
  from settings import *
except ImportError as e:
  print(f'Error loading settings: {type(e).__name__}: {e}')

from terms import *

import time

import board
import busio
from adafruit_debouncer import Button
from digitalio import DigitalInOut, Direction, Pull
from microcontroller import Pin

serial: busio.UART|None = None

buttons: tuple[Button, ...]
button_select_bit: Button
button_select_pixel: Button
button_brightness: Button
buttons_quantity: tuple[Button, Button, Button]

def init():
  pass

def loop():
  update_buttons()

def update_buttons():
  for i, button in enumerate(buttons):
    button.update()
    if button.pressed:
      print(f'{i=} pressed')
  for i, button in enumerate(buttons_quantity):
    if not button.short_count:
      continue
    if button_brightness.function():
      verb = VERB_ADJUST
      key = KEY_BRIGHTNESS
    elif button_select_bit.function():
      verb = VERB_SELECT
      key = KEY_BIT
    elif button_select_pixel.function():
      verb = VERB_SELECT
      key = KEY_PIXEL
    else:
      verb = VERB_ADJUST
      key = KEY_INTENSITY
    if i == 0:
      quantity = None
    elif i == 1:
      quantity = -button.short_count
    elif i == 2:
      quantity = button.short_count
    if quantity and key == KEY_BRIGHTNESS:
      quantity = quantity / 10
    cmdstr = f'{verb}{key}'
    if quantity:
      cmdstr = f'{cmdstr} {quantity}'
    print(f'{verb=} {key=} {quantity=} {cmdstr=}')
    serial.write(f'{cmdstr}\n'.encode())


def init_pullup(pin: str):
  io = DigitalInOut(getattr(board, pin))
  io.direction = Direction.INPUT
  io.pull = Pull.UP
  return io

def init_button(pin: Pin):
  return Button(
    pin,
    short_duration_ms=50,
    long_duration_ms=long_duration_ms)

_button_pins = ()
try:
  serial = busio.UART(
    board.TX,
    None,
    baudrate=baudrate)
  _button_pins = tuple(map(init_pullup, button_pins))
  buttons = tuple(map(init_button, _button_pins))
  button_select_bit = buttons[0]
  button_select_pixel = buttons[1]
  button_brightness = buttons[2]
  buttons_quantity = buttons[3:]
  init()
  while True:
    loop()
finally:
  if serial:
    serial.deinit()
  for pin in _button_pins:
    pin.deinit()
    
