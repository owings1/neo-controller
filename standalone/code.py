from __future__ import annotations

import board
import busio
import keypad
from classes import *
from neopixel import NeoPixel
from neopixel_spi import NeoPixel_SPI
from utils import settings


class App:
  animator: Animator|None = None
  changer: Changer|None = None
  spi: busio.SPI|None = None
  pixels: NeoPixel|NeoPixel_SPI|None = None
  keys: keypad.Keys|None = None
  buttons: Buttons|None = None

  def main(self) -> None:
    try:
      self.init()
      print(f'Running loop')
      while True:
        self.loop()
    except KeyboardInterrupt:
      print(f'Stopping from Ctrl-C')
    finally:
      self.deinit()
  
  def init(self) -> None:
    self.deinit()
    initial_brightness = settings.initial_brightness / settings.brightness_scale
    print(
      f'Initializing {settings.num_pixels} pixels '
      f'on {settings.data_pin} '
      f'{initial_brightness=}')
    if settings.data_pin == 'SPI':
      self.spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
      neocls = NeoPixel_SPI
    else:
      neocls = NeoPixel
    self.pixels = neocls(
      self.spi or settings.data_pin,
      settings.num_pixels,
      brightness=initial_brightness,
      auto_write=False,
      pixel_order=settings.pixel_order)
    self.keys = keypad.Keys(
      tuple(getattr(board, pin) for pin in (
        settings.b0_pin,
        settings.b1_pin,
        settings.b2_pin)),
      value_when_pressed=False,
      pull=True)
    self.buttons = Buttons(self.keys)
    self.animator = Animator(self.pixels)
    self.changer = Changer(self.pixels)
    self.animator.routine = settings.initial_routine
  
  def deinit(self) -> None:
    if self.changer:
      self.changer.deinit()
    if self.pixels:
      self.pixels.deinit()
    if self.spi:
      self.spi.deinit()
    if self.animator:
      self.animator.deinit()
    if self.buttons:
      self.buttons.deinit()
    if self.keys:
      self.keys.deinit()
  
  def loop(self) -> None:
    event = self.buttons.run()
    if event:
      self.handle(event)
    self.animator.run()

  def handle(self, event: KeyEvent) -> None:
    print(f'{event=}')
    if not event.held:
      if event.key == 1 and event.type == 'short':
        self.changer.brightness('minus', 1)
      elif event.key == 2 and event.type == 'short':
        self.changer.brightness('plus', 1)
    elif event.held == {0}:
      if event.key == 1 and event.type == 'short':
        self.animator.speed_change('minus', 1)
      elif event.key == 2 and event.type == 'short':
        self.animator.speed_change('plus', 1)
    elif event.held == {1}:
      if event.key == 2 and event.type == 'short':
        self.animator.routine_change('plus', 1)

app = App()

del(App)

if __name__ == '__main__':
  app.main()
