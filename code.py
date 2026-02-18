from __future__ import annotations

import board
import busio
import displayio
import keypad
from adafruit_ticks import ticks_diff, ticks_ms
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
  rotary: Rotary|None = None
  i2c: busio.I2C|None = None
  oled: Oled|None = None
  change_mode: int = 0
  last_active_ms: int = 0

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
      self.spi = busio.SPI(
        clock=board.SCK,
        MOSI=board.MOSI,
        MISO=board.MISO)
      neocls = NeoPixel_SPI
    else:
      neocls = NeoPixel
    self.pixels = neocls(
      self.spi or settings.data_pin,
      settings.num_pixels,
      brightness=initial_brightness,
      auto_write=False,
      pixel_order=settings.pixel_order)
    if settings.rotary_enabled:
      self.i2c = self.i2c or busio.I2C(board.SCL, board.SDA)
      self.rotary = Rotary(
        i2c=self.i2c,
        int_pin=getattr(board, settings.rotary_int_pin),
        address=settings.rotary_address,
        reverse=settings.rotary_reverse,
        handler=self.handle_rotary)
    if settings.buttons_enabled:
      button_pins = [
        getattr(board, pin) for pin in (
          settings.b0_pin,
          settings.b1_pin,
          settings.b2_pin)]
      if settings.buttons_reversed:
        button_pins.reverse()
      self.keys = keypad.Keys(
        button_pins,
        value_when_pressed=False,
        pull=True)
      self.buttons = Buttons(
        keys=self.keys,
        handler=self.handle_button)
    if settings.oled_enabled:
      self.i2c = self.i2c or busio.I2C(board.SCL, board.SDA)
      self.oled = Oled(
        i2c=self.i2c,
        address=settings.oled_address,
        width=settings.oled_width,
        height=settings.oled_height,
        line_spacing=settings.oled_line_spacing)
    self.changer = Changer(self.pixels)
    self.animator = Animator(self.pixels)
    self.animator.routine = settings.initial_routine
    self.draw_display()
    self.last_active_ms = ticks_ms()
  
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
    if self.rotary:
      self.rotary.deinit()
    if self.oled:
      self.oled.deinit()
    displayio.release_displays()
    if self.i2c:
      self.i2c.deinit()
    self.change_mode = 0

  def loop(self) -> None:
    self.animator.run()
    if self.buttons and self.buttons.run():
      self.last_active_ms = ticks_ms()
      self.draw_display()
      return
    if self.rotary and self.rotary.run():
      self.last_active_ms = ticks_ms()
      self.draw_display()
      return
    if self.idle_ms > settings.idle_ms:
      if self.change_mode != 0:
        self.change_mode = 0
      if self.oled and self.oled.display.is_awake:
        self.oled.display.sleep()

  @property
  def idle_ms(self) -> int:
    return ticks_diff(ticks_ms(), self.last_active_ms)

  def handle_button(self, event: KeyEvent) -> None:
    print(f'{event=}')
    if self.oled and not self.oled.display.is_awake:
      self.oled.display.wake()
      return
    if event.held:
      return
    if event.key == 2:
      if self.change_mode == 0:
        if event.type == 'short':
          self.changer.brightness('plus', 1)
        elif event.type == 'long':
          self.changer.brightness('max', None)
      elif self.change_mode == 1:
        if event.type == 'short':
          self.animator.speed_change('plus', 1)
        elif event.type == 'long':
          self.animator.speed_change('max', None)
      elif self.change_mode == 2:
        if event.type == 'short':
          self.animator.routine_change('plus', 1)
        elif event.type == 'long':
          self.animator.routine_change('max', None)
    elif event.key == 0:
      if self.change_mode == 0:
        if event.type == 'short':
          self.changer.brightness('minus', 1)
        elif event.type == 'long':
          self.changer.brightness('min', None)
      elif self.change_mode == 1:
        if event.type == 'short':
          self.animator.speed_change('minus', 1)
        elif event.type == 'long':
          self.animator.speed_change('min', None)
      elif self.change_mode == 2:
        if event.type == 'short':
          self.animator.routine_change('minus', 1)
        elif event.type == 'long':
          self.animator.routine_change('min', None)
    elif event.key == 1:
      if event.type == 'short':
        if self.change_mode == 2:
          self.change_mode = 0
        else:
          self.change_mode += 1
      elif event.type == 'long':
        self.change_mode = 0

  def handle_rotary(self, event: str) -> None:
    print(f'{event=}')
    if event == 'push':
      return
    if self.oled and not self.oled.display.is_awake:
      self.oled.display.wake()
      return
    if event == 'increment':
      if self.change_mode == 0:
        self.changer.brightness('plus', 1)
      elif self.change_mode == 1:
        self.animator.speed_change('plus', 1)
      elif self.change_mode == 2:
        self.animator.routine_change('plus', 1)
    elif event == 'decrement':
      if self.change_mode == 0:
        self.changer.brightness('minus', 1)
      elif self.change_mode == 1:
        self.animator.speed_change('minus', 1)
      elif self.change_mode == 2:
        self.animator.routine_change('minus', 1)
    elif event == 'release':
      if self.change_mode == 2:
        self.change_mode = 0
      else:
        self.change_mode += 1
    elif event == 'double_push':
      self.change_mode = 0

  def draw_display(self) -> None:
    if not self.oled:
      return
    if self.change_mode == 0:
      self.oled.header = 'Brightness'
      self.oled.body = str(self.pixels.brightness)
    elif self.change_mode == 1:
      self.oled.header = 'Speed'
      self.oled.body = str(self.animator.speed)
    elif self.change_mode == 2:
      self.oled.header = 'Routine'
      self.oled.body = self.animator.routine
    if not self.oled.display.is_awake:
      self.oled.display.wake()

app = App()

del(App)

if __name__ == '__main__':
  app.main()
