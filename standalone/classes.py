from __future__ import annotations

import math
import random
import time
from collections import namedtuple

import keypad
import utils
from adafruit_ticks import ticks_diff, ticks_ms
from utils import ColorType, settings

__all__ = (
  'Animator',
  'Buttons',
  'Changer',
  'KeyEvent')

class Changer:
  pixels: NeoPixel

  def __init__(self, pixels: NeoPixel) -> None:
    self.pixels = pixels

  def deinit(self) -> None:
    pass

  def brightness(self, verb: str, quantity: int|None) -> None:
    if verb == 'clear':
      value = settings.initial_brightness
    elif verb == 'set':
      value = quantity
    elif verb == 'minus':
      value = math.ceil(self.pixels.brightness * settings.brightness_scale) - quantity
    else:
      value = int(self.pixels.brightness * settings.brightness_scale) + quantity
    value = max(0, min(settings.brightness_scale, value)) / settings.brightness_scale
    change = value != self.pixels.brightness
    print(f'brightness={self.pixels.brightness} {change=}')
    if change:
      self.pixels.brightness = value
      self.pixels.show()

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
      self.anim.interval = settings.speeds[self._speed]

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
    print(f'routine={value}')
    func = getattr(self, f'anim_{value}')
    self.clear()
    self.anim = func()
    self.anim.start()
    self._routine = value

  def deinit(self) -> None:
    self.clear()

  def run(self):
    if self.anim:
      try:
        self.anim.run()
      except StopIteration:
        self.clear()

  def speed_change(self, verb: str, quantity: int|None) -> None:
    if quantity is None:
      self.speed = settings.initial_speed
    else:
      self.speed = utils.resolve_index_change(
        verb,
        quantity,
        self.speed,
        len(settings.speeds),
        False)
    print(f'speed={self.speed} interval={settings.speeds[self.speed]}')

  def routine_change(self, verb: str, quantity: int|None) -> None:
    if quantity is None:
      self.routine = settings.initial_routine
    else:
      self.routine = self.routines[
        utils.resolve_index_change(
          'plus',
          1,
          self.routines.index(self.routine),
          len(self.routines),
          True)]
    print(f'routine={self.routine}')

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

  def ready(self) -> None:
    return self.at is not None and time.monotonic_ns() - self.at >= 0

  def run(self) -> None:
    if self.ready():
      self.tick()
      self.at = time.monotonic_ns() + self.interval * 1000 * settings.min_micros_interval * self.interval_coeff

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
  long_duration: int = 1000

  def __init__(self, keys: keypad.Keys):
    self.keys = keys
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
    presstype = 'long' if duration >= self.long_duration else 'short'
    held: set[int] = set()
    for i, s in enumerate(self.states):
      if i != event.key_number:
        if s.pressed_at is not None:
          held.add(i)
        # Clear last release
        s.released_at = None
    return KeyEvent(event.key_number, presstype, held)

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

# Typing
try:
  from neopixel import NeoPixel
  from typing import ClassVar, Iterable, Sequence
except ImportError:
  pass
