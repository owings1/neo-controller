from __future__ import annotations

import math
import random
import time
from collections import namedtuple

import digitalio
import displayio
import fontio
import i2cdisplaybus
import i2cencoderlibv21
import keypad
import rotaryio
import terminalio
import utils
from adafruit_display_text.label import Label
from adafruit_displayio_ssd1306 import SSD1306
from adafruit_ticks import ticks_diff, ticks_ms
from busio import I2C
from i2cencoderlibv21 import I2CEncoderLibV21
from microcontroller import Pin
from utils import ColorType, settings

__all__ = (
  'Animator',
  'Buttons',
  'Changer',
  'I2CRotary',
  'KeyEvent',
  'Oled',
  'PlainRotary',
  'Rotary')

class Changer:
  pixels: NeoPixel

  def __init__(self, pixels: NeoPixel) -> None:
    self.pixels = pixels

  def deinit(self) -> None:
    pass

  def brightness(self, verb: str, quantity: int|None) -> None:
    if verb == 'clear':
      value = settings.initial_brightness
    elif verb == 'min':
      value = 0
    elif verb == 'max':
      value = settings.brightness_scale
    elif verb == 'set':
      value = quantity
    elif verb == 'minus':
      value = math.ceil(self.pixels.brightness * settings.brightness_scale) - quantity
    else:
      value = int(self.pixels.brightness * settings.brightness_scale) + quantity
    value = max(0, min(settings.brightness_scale, value)) / settings.brightness_scale
    change = value != self.pixels.brightness
    if change:
      self.pixels.brightness = value
      self.pixels.show()
    print(f'brightness={self.pixels.brightness} {change=}')

class Animator:
  routines: ClassVar[Sequence[str]] = (
    'wheel_loop',
    'red_loop',
    'blue_loop',
    'green_loop',
    'rando')
  pixels: NeoPixel
  anim: Animation|None = None
  _speed: int
  _routine: str|None = None
  
  def __init__(self, pixels: NeoPixel) -> None:
    self.pixels = pixels
    self.speed = settings.initial_speed

  @property
  def speed(self) -> int:
    return self._speed

  @speed.setter
  def speed(self, value: int) -> None:
    self._speed = max(0, min(value, len(settings.speeds) - 1))
    if self.anim:
      self.anim.interval = self.interval
    print(f'speed={self.speed} interval={self.interval}')

  @property
  def interval(self) -> int:
    return settings.speeds[self.speed]

  @property
  def routine(self) -> str|None:
    return self._routine

  @routine.setter
  def routine(self, value: str) -> None:
    if value not in self.routines:
      raise ValueError(f'routine={value}')
    func = getattr(self, f'anim_{value}')
    self.clear()
    self.anim = func()
    self.anim.start()
    self._routine = value
    print(f'routine={self.routine}')

  def deinit(self) -> None:
    self.clear()

  def run(self) -> bool:
    if self.anim:
      try:
        return self.anim.run()
      except StopIteration:
        self.clear()
    return False

  def speed_change(self, verb: str, quantity: int|None) -> None:
    if verb == 'clear':
      self.speed = settings.initial_speed
    else:
      self.speed = utils.resolve_index_change(
        verb,
        quantity,
        self.speed,
        len(settings.speeds),
        False)

  def routine_change(self, verb: str, quantity: int|None) -> None:
    if verb == 'clear':
      self.routine = settings.initial_routine
    else:
      self.routine = self.routines[
        utils.resolve_index_change(
          verb,
          quantity,
          self.routines.index(self.routine),
          len(self.routines),
          True)]

  def clear(self) -> None:
    self.anim = None

  def anim_wheel_loop(self) -> Animation:
    return PathAnimation(
      self.pixels,
      path=utils.repeat((0xff0000, 0xff00, 0xff)),
      interval=self.interval,
      steps=settings.transition_steps)

  def anim_red_loop(self) -> Animation:
    return PathAnimation(
      self.pixels,
      path=utils.repeat((0xff0000, 0xff00ff)),
      interval=self.interval,
      steps=settings.transition_steps)

  def anim_blue_loop(self) -> Animation:
    return PathAnimation(
      self.pixels,
      path=utils.repeat((0xff, 0xff00ff)),
      interval=self.interval,
      steps=settings.transition_steps)

  def anim_green_loop(self) -> Animation:
    return PathAnimation(
      self.pixels,
      path=utils.repeat((0xff00, 0xffff)),
      interval=self.interval,
      steps=settings.transition_steps)

  def anim_rando(self) -> Animation:
    def getbuf():
      for _ in anim.pixels:
        if random.random() <= settings.rando_fillchance:
          yield random.randint(0, 0xffffff)
        else:
          yield 0
    def bufiter():
      while True:
        yield getbuf()
    anim = Animation(
      self.pixels,
      interval=self.interval,
      it=bufiter())
    anim.interval_coeff = 10
    return anim

class Animation:
  pixels: NeoPixel
  interval: int
  at: int|None = None
  it: Iterable[Iterable[ColorType]]
  interval_coeff: int = 1

  def __init__(self, pixels: NeoPixel, interval: int, it: Iterable[Iterable[ColorType]]) -> None:
    self.pixels = pixels
    self.interval = interval
    self.it = it

  def start(self) -> None:
    self.at = time.monotonic_ns()

  def ready(self) -> bool:
    return self.at is not None and time.monotonic_ns() - self.at >= 0

  def run(self) -> bool:
    if self.ready():
      self.tick()
      self.at = time.monotonic_ns() + self.interval * 1000 * settings.min_micros_interval * self.interval_coeff
      return True
    return False

  def tick(self) -> None:
    change = False
    for p, value in enumerate(next(self.it)):
      if change or self.pixels[p] != utils.as_tuple(value):
        change = True
        self.pixels[p] = value
    if change:
      self.pixels.show()   

class PathAnimation(Animation):
  'Transition through color path'

  def __init__(self, pixels: NeoPixel, path: Iterable[ColorType], interval: int, steps: int) -> None:
    def bufiter():
      trit = utils.transitions(path, steps)
      yield (next(trit) for _ in self.pixels)
      r = range(1, len(self.pixels))
      def gennext():
        c = next(trit)
        for i in r:
          yield self.pixels[i]
        yield c
      while True:
        yield gennext()
    super().__init__(pixels, interval, bufiter())

class Buttons:
  keys: keypad.Keys
  long_duration_ms: int = settings.buttons_long_duration_ms
  handler: Callable[[KeyEvent], None]|None = None

  def __init__(self, keys: keypad.Keys, handler: Callable[[KeyEvent], None]|None = None):
    self.keys = keys
    self.handler = handler
    self.states = [KeyState() for _ in range(self.keys.key_count)]

  def run(self) -> KeyEvent|None:
    event = self.keys.events.get()
    if not event:
      return
    state = self.states[event.key_number]
    if event.pressed:
      state.pressed_at = ticks_ms()
      return
    if state.pressed_at is None:
      # Anomalous release event without known pressed event
      state.released_at = None
      return
    state.released_at = ticks_ms()
    duration = ticks_diff(state.released_at, state.pressed_at)
    # Clear pressed at
    state.pressed_at = None
    presstype = 'long' if duration >= self.long_duration_ms else 'short'
    held: set[int] = set()
    for i, s in enumerate(self.states):
      if i != event.key_number:
        if s.pressed_at is not None:
          held.add(i)
        # Clear last release
        s.released_at = None
    keyevent = KeyEvent(event.key_number, presstype, held)
    if self.handler:
      self.handler(keyevent)
    return keyevent

  def deinit(self) -> None:
    for state in self.states:
      state.clear()

class KeyState:
  pressed_at: int|None = None
  released_at: int|None = None

  def clear(self) -> None:
    self.pressed_at = None
    self.released_at = None

class KeyEvent(namedtuple('KeyEventBase', ('key', 'type', 'held'))):
  key: int
  type: str
  held: set[int]

class Rotary:
  handler: Callable[[str], None]|None = None

  def run(self) -> bool:
    return False

  def deinit(self) -> None:
    pass

class I2CRotary(Rotary):
  encoder: I2CEncoderLibV21
  int: digitalio.DigitalInOut
  config = i2cencoderlibv21.IPUP_DISABLE

  def __init__(
    self,
    i2c: I2C,
    int_pin: Pin,
    address: int,
    reverse: bool = False,
    handler: Callable[[str], None]|None = None,
  ) -> None:
    self.encoder = I2CEncoderLibV21(i2c, address)
    self.encoder.reset()
    self.int = digitalio.DigitalInOut(int_pin)
    self.int.direction = digitalio.Direction.INPUT
    self.int.pull = digitalio.Pull.UP
    self.handler = handler
    if reverse:
      self.config |= i2cencoderlibv21.DIRE_LEFT

    def make_handler(event: str):
      def handler():
        if self.handler:
          self.handler(event)
        else:
          print(f'{event=}')
      return handler

    self.encoder.onIncrement = make_handler('increment')
    self.encoder.onDecrement = make_handler('decrement')
    self.encoder.onButtonRelease = make_handler('release')
    self.encoder.onButtonPush = make_handler('push')
    self.encoder.onButtonDoublePush = make_handler('double_push')
    time.sleep(0.001)
    self.encoder.begin(self.config)
    self.encoder.write_antibounce_period(settings.rotary_antibounce_period)
    self.encoder.write_double_push_period(settings.rotary_double_push_period)
    self.encoder.autoconfig_interrupt()

  def run(self) -> bool:
    if not self.int.value:
      self.encoder.update_status()
      return True
    return False

  def deinit(self) -> None:
    self.int.deinit()

class PlainRotary(Rotary):
  encoder: rotaryio.IncrementalEncoder
  button: digitalio.DigitalInOut
  last_pos: int
  button_state: bool = False
  first_push_at: int|None = None
  last_release_at: int|None = None
  last_push_at: int|None = None

  def __init__(
    self,
    pin_a: Pin,
    pin_b: Pin,
    button_pin: Pin,
    reverse: bool = False,
    handler: Callable[[str], None]|None = None,
  ) -> None:
    self.handler = handler
    if reverse:
      pin_a, pin_b = pin_b, pin_a
    self.encoder = rotaryio.IncrementalEncoder(pin_a, pin_b, settings.rotary_divisor)
    self.last_pos = self.encoder.position
    self.button = digitalio.DigitalInOut(button_pin)
    self.button.direction = digitalio.Direction.INPUT
    self.button.pull = digitalio.Pull.UP

  def run(self) -> bool:
    if self.last_release_at:
      if ticks_diff(ticks_ms(), self.first_push_at) > settings.rotary_double_push_period * 10:
        self.first_push_at = None
        self.last_release_at = None
        self.emit('push')
        self.emit('release')
        return True
    pos = self.encoder.position
    change, self.last_pos = pos - self.last_pos, pos
    if change > 0:
      self.emit('increment')
      return True
    if change < 0:
      self.emit('decrement')
      return True
    if not self.button.value and not self.button_state:
      self.button_state = True
      self.last_push_at = ticks_ms()
      return False
    if self.button.value and self.button_state:
      self.button_state = False
      if self.last_release_at:
        if ticks_diff(ticks_ms(), self.first_push_at) <= settings.rotary_double_push_period * 10:
          self.first_push_at = None
          self.last_release_at = None
          self.emit('double_push')
          return True
      self.first_push_at = self.last_push_at
      self.last_release_at = ticks_ms()
      return False
    return False

  def emit(self, event: str) -> None:
    if self.handler:
      self.handler(event)
    else:
      print(f'{event=}')

  def deinit(self) -> None:
    self.encoder.deinit()
    self.button.deinit()

class Oled:
  display: SSD1306

  def __init__(
    self,
    i2c: I2C,
    address: int,
    width: int,
    height: int,
    line_spacing: int = 4,
    font: fontio.FontProtocol = terminalio.FONT,
  ) -> None:
    self.display = SSD1306(
      bus=i2cdisplaybus.I2CDisplayBus(
        i2c_bus=i2c,
        device_address=address),
      width=width,
      height=height)
    self.splash = displayio.Group()
    self.display.root_group = self.splash
    grid = displayio.TileGrid(
      displayio.Bitmap(width, height, 1),
      pixel_shader=displayio.Palette(1))
    grid.pixel_shader[0] = 0x0
    self.splash.append(grid)
    fbb = font.get_bounding_box()
    self.text_width = width // fbb[0]
    self.labels = (
      Label(
        font,
        text=' ' * self.text_width,
        color=0xffffff,
        x=0,
        y=fbb[1] // 2),
      Label(
        font,
        text=' ' * self.text_width,
        color=0xffffff,
        x=0,
        y=fbb[1] // 2 + fbb[1] + line_spacing + 1))      
    for label in self.labels:
      self.splash.append(label)

  @property
  def header(self) -> str:
    return self.labels[0].text.strip()

  @header.setter
  def header(self, value: str) -> None:
    value = value[:self.text_width]
    if self.labels[0].text != value:
      self.labels[0].text = value

  @property
  def body(self) -> str:
    return self.labels[1].text.strip()

  @body.setter
  def body(self, value: str) -> None:
    value = value[:self.text_width]
    if self.labels[1].text != value:
      self.labels[1].text = value

  def deinit(self) -> None:
    for _ in self.labels:
      self.splash.pop()
    self.display.refresh()
    self.display.sleep()

# Typing
try:
  from neopixel import NeoPixel
  from typing import Callable, ClassVar, Iterable, Sequence
except ImportError:
  pass
