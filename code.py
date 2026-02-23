from __future__ import annotations

import board
import busio
import keypad
from adafruit_ticks import ticks_diff, ticks_ms
from neopixel import NeoPixel

from classes import *
from utils import as_pin, settings


class App:
  animator: Animator|None = None
  changer: Changer|None = None
  spi: busio.SPI|None = None
  pixels: NeoPixel|None = None
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
      from neopixel_spi import NeoPixel_SPI as NeoPixel
      self.spi = board.SPI()
    else:
      from neopixel import NeoPixel
    self.pixels = NeoPixel(
      self.spi or as_pin(settings.data_pin),
      settings.num_pixels,
      brightness=initial_brightness,
      auto_write=False,
      pixel_order=settings.pixel_order)
    if settings.rotary_enabled:
      if settings.rotary_i2c:
        self.i2c = board.I2C()
        self.rotary = I2CRotary(
          i2c=self.i2c,
          interrupt_pin=settings.rotary_interrupt_pin,
          address=settings.rotary_address,
          reverse=settings.rotary_reverse,
          handler=self.handle_rotary)
      else:
        self.rotary = PlainRotary(
          pin_a=settings.rotary_pin_a,
          pin_b=settings.rotary_pin_b,
          button_pin=settings.rotary_button_bin,
          reverse=settings.rotary_reverse,
          handler=self.handle_rotary)
    if settings.buttons_enabled:
      button_pins = [
        as_pin(pin) for pin in (
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
      if settings.oled_bus == 'I2C':
        from i2cdisplaybus import I2CDisplayBus
        self.i2c = board.I2C()
        display_bus = I2CDisplayBus(
          i2c_bus=self.i2c,
          device_address=settings.oled_address)
      elif settings.oled_bus == 'SPI':
        from fourwire import FourWire
        self.spi = board.SPI()
        display_bus = FourWire(
          spi_bus=self.spi,
          command=as_pin(settings.oled_dc_pin),
          chip_select=as_pin(settings.oled_cs_pin),
          reset=as_pin(settings.oled_reset_pin))
      else:
        raise RuntimeError(f'Invalid display bus type: {settings.oled_bus}')
      self.oled = Oled(
        bus=display_bus,
        driver=settings.oled_driver,
        width=settings.oled_width,
        height=settings.oled_height,
        line_spacing=settings.oled_line_spacing,
        x_offset=settings.oled_x_offset)
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
      import displayio
      displayio.release_displays()
    if self.i2c:
      self.i2c.deinit()
    if self.spi:
      self.spi.deinit()
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
      if self.oled:
        self.oled.sleep()

  @property
  def idle_ms(self) -> int:
    return ticks_diff(ticks_ms(), self.last_active_ms)

  def handle_button(self, event: KeyEvent) -> None:
    print(f'{event=}')
    if self.oled and not self.oled.is_awake:
      self.oled.wake()
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
    if self.oled and not self.oled.is_awake:
      self.oled.wake()
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
      title = self.animator.routine.replace('_', ' ')
      title = title[:1].upper() + title[1:]
      self.oled.body = title
    self.oled.wake()

app = App()

del(App)

if __name__ == '__main__':
  app.main()
