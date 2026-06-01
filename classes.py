from __future__ import annotations

import math
import random
import time
from collections import namedtuple

import displayio
import fontio
import keypad
import terminalio
from adafruit_ticks import ticks_diff, ticks_ms
from busdisplay import BusDisplay
from busio import I2C
from digitalio import DigitalInOut, Direction, Pull
from fourwire import FourWire
from i2cdisplaybus import I2CDisplayBus
from microcontroller import Pin

import utils
from utils import ColorType, as_pin, settings

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
  pixels: NeoPixelType

  def __init__(self, pixels: NeoPixelType) -> None:
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
  pixels: NeoPixelType
  anim: Animation|None = None
  _speed: int
  _routine: str|None = None
  
  def __init__(self, pixels: NeoPixelType) -> None:
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
  pixels: NeoPixelType
  interval: int
  at: int|None = None
  it: Iterable[Iterable[ColorType]]
  interval_coeff: int = 1

  def __init__(self, pixels: NeoPixelType, interval: int, it: Iterable[Iterable[ColorType]]) -> None:
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

  def __init__(self, pixels: NeoPixelType, path: Iterable[ColorType], interval: int, steps: int) -> None:
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

  def __init__(self, pins: Sequence[str|Pin], reverse: bool = False, handler: Callable[[KeyEvent], None]|None = None):
    pins = [as_pin(pin) for pin in pins]
    if reverse:
      pins.reverse()

    self.keys = keypad.Keys(
      pins,
      value_when_pressed=False,
      pull=True)
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
    self.keys.deinit()

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
  encoder: i2cencoderlibv21.I2CEncoderLibV21
  interrupt: DigitalInOut

  def __init__(
    self,
    i2c: I2C,
    interrupt_pin: str|Pin,
    address: int,
    reverse: bool = False,
    handler: Callable[[str], None]|None = None,
  ) -> None:
    import i2cencoderlibv21
    self.encoder = i2cencoderlibv21.I2CEncoderLibV21(i2c, address)
    self.encoder.reset()
    self.interrupt = DigitalInOut(as_pin(interrupt_pin))
    self.interrupt.direction = Direction.INPUT
    self.interrupt.pull = Pull.UP
    self.handler = handler
    config = i2cencoderlibv21.IPUP_DISABLE
    if reverse:
      config |= i2cencoderlibv21.DIRE_LEFT

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
    # Ensure reset is complete, 400us
    time.sleep(0.001)
    self.encoder.begin(config)
    self.encoder.write_antibounce_period(settings.rotary_antibounce_period)
    self.encoder.write_double_push_period(settings.rotary_double_push_period)
    self.encoder.autoconfig_interrupt()

  def run(self) -> bool:
    if not self.interrupt.value:
      self.encoder.update_status()
      return True
    return False

  def deinit(self) -> None:
    self.interrupt.deinit()

class PlainRotary(Rotary):
  encoder: rotaryio.IncrementalEncoder
  button: DigitalInOut
  last_pos: int
  button_state: bool = False
  first_push_at: int|None = None
  last_release_at: int|None = None
  last_push_at: int|None = None
  double_push_period: int = settings.rotary_double_push_period * 10

  def __init__(
    self,
    pin_a: str|Pin,
    pin_b: str|Pin,
    button_pin: str|Pin,
    reverse: bool = False,
    handler: Callable[[str], None]|None = None,
  ) -> None:
    import rotaryio
    self.handler = handler
    if reverse:
      pin_a, pin_b = pin_b, pin_a
    self.encoder = rotaryio.IncrementalEncoder(
      as_pin(pin_a),
      as_pin(pin_b),
      settings.rotary_divisor)
    self.last_pos = self.encoder.position
    self.button = DigitalInOut(as_pin(button_pin))
    self.button.direction = Direction.INPUT
    self.button.pull = Pull.UP

  def run(self) -> bool:
    if self.last_release_at:
      if ticks_diff(ticks_ms(), self.first_push_at) > self.double_push_period:
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
        if ticks_diff(ticks_ms(), self.first_push_at) <= self.double_push_period:
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
  display: BusDisplay
  driver: str
  sleepable: bool
  text_width: int
  lines: tuple[Label, Label]

  def __init__(
    self,
    bus: I2CDisplayBus|FourWire,
    driver: str,
    width: int,
    height: int,
    line_spacing: int = 4,
    x_offset: int = 0,
    font: fontio.FontProtocol = terminalio.FONT,
  ) -> None:
    if driver == 'SSD1305':
      from adafruit_displayio_ssd1305 import SSD1305 as Driver
    elif driver == 'SSD1306':
      from adafruit_displayio_ssd1306 import SSD1306 as Driver
    elif driver == 'SH1106':
      from adafruit_displayio_sh1106 import SH1106 as Driver
    elif driver == 'SH1107':
      from adafruit_displayio_sh1107 import SH1107 as Driver
    elif driver == 'ST7735':
      from adafruit_st7735 import ST7735 as Driver
    elif driver == 'ST7735R':
      from adafruit_st7735r import ST7735R as Driver
    else:
      raise RuntimeError(f'Unsupported driver: {driver}')
    from adafruit_display_text.label import Label
    self.driver = driver
    self.display = Driver(
      bus=bus,
      width=width,
      height=height)
    self.sleepable = hasattr(self.display, 'sleep')
    self.display.root_group = displayio.Group()
    # Clear display
    blank_palette = displayio.Palette(1)
    blank_palette[0] = 0x0
    self.display.root_group.append(
      displayio.TileGrid(
        displayio.Bitmap(width, height, 1),
        pixel_shader=blank_palette,
        x=x_offset))
    fbb = font.get_bounding_box()
    self.text_width = (width - x_offset) // fbb[0]
    self.lines = (
      Label(
        font,
        text=' ' * self.text_width,
        color=0xffffff,
        x=x_offset,
        y=fbb[1] // 2),
      Label(
        font,
        text=' ' * self.text_width,
        color=0xffffff,
        x=x_offset,
        y=fbb[1] // 2 + fbb[1] + line_spacing + 1))      
    for label in self.lines:
      self.display.root_group.append(label)

  @property
  def header(self) -> str:
    return self.lines[0].text.strip()

  @header.setter
  def header(self, value: str) -> None:
    value = value[:self.text_width]
    if self.lines[0].text != value:
      self.lines[0].text = value

  @property
  def body(self) -> str:
    return self.lines[1].text.strip()

  @body.setter
  def body(self, value: str) -> None:
    value = value[:self.text_width]
    if self.lines[1].text != value:
      self.lines[1].text = value

  def deinit(self) -> None:
    for _ in self.lines:
      self.display.root_group.pop()
    self.display.refresh()
    self.sleep()

  def sleep(self) -> None:
    if self.sleepable:
      if self.driver == 'SH1106':
        # Patch for bug in SH1106 driver: TypeError: object with buffer protocol required
        if self.display._is_awake:
          self.display.bus.send(0xae, bytearray())
          self.display._is_awake = False
      else:
        self.display.sleep()

  def wake(self) -> None:
    if self.sleepable:
      if self.driver == 'SH1106':
        # Patch for bug in SH1106 driver: TypeError: object with buffer protocol required
        if not self.display._is_awake:
          self.display.bus.send(0xaf, bytearray())
          self.display._is_awake = True
      else:
        self.display.wake()

  @property
  def is_awake(self) -> bool:
    return not self.sleepable or self.display.is_awake

# Typing
try:
  from typing import Callable, ClassVar, Iterable, Sequence, TYPE_CHECKING
  from neopixel import NeoPixel as NeoPixelType
  from adafruit_display_text.label import Label
  import i2cencoderlibv21
  import rotaryio # not available on ESP32C3
  __all__ += ('NeoPixelType',)
except ImportError:
  pass
