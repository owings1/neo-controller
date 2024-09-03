from __future__ import annotations

import traceback

import board
import busio
from classes import *
from neopixel import NeoPixel
from utils import settings

import terms

try:
  from typing import Self
except ImportError:
  pass

class App:

  animator: Animator|None = None
  bufstore: BufStore|None = None
  changer: Changer|None = None
  commander: Commander|None = None
  leds: ActLeds|None = None
  pixels: NeoPixel|None = None
  sd: SdReader|None = None
  serial: busio.UART|None = None

  INSTANCE: Self = None

  def __new__(cls) -> Self:
    cls.INSTANCE = cls.INSTANCE or super().__new__(cls)
    return cls.INSTANCE

  def main(self) -> None:
    try:
      self.init()
      while True:
        self.loop()
    except KeyboardInterrupt:
      print(f'Stopping from Ctrl-C')
    finally:
      self.deinit()
  
  def init(self) -> None:
    self.deinit()

    Animator.speeds = settings.speeds
    BufStore.fallback_color = settings.initial_color
    Changer.brightness_scale = settings.brightness_scale
    Changer.initial_brightness = settings.initial_brightness
    Changer.initial_color = settings.initial_color
    SdReader.enabled = settings.sd_enabled

    self.pixels = NeoPixel(
      getattr(board, settings.data_pin),
      settings.num_pixels,
      brightness=(
        settings.initial_brightness /
        settings.brightness_scale),
      auto_write=False,
      pixel_order=settings.pixel_order)
    self.sd = SdReader(board.SPI(), getattr(board, settings.sd_cs_pin))
    self.bufstore = BufStore(self.pixels, self.sd, settings.num_presets)
    self.animator = Animator(self.pixels, self.bufstore)
    self.serial = busio.UART(
      None,
      board.RX,
      baudrate=settings.baudrate,
      timeout=settings.serial_timeout)
    self.leds = ActLeds.frompins(board.LED_GREEN, board.LED_BLUE)
    self.commander = Commander(self.serial, self.leds)
    self.changer = Changer(self.pixels)

    self.sd.remount()
    self.bufstore.restore(0)
  
  def deinit(self) -> None:
    if self.commander:
      self.commander.deinit()
    if self.changer:
      self.changer.deinit()
    if self.serial:
      self.serial.deinit()
    if self.pixels:
      self.pixels.deinit()
    if self.leds:
      self.leds.deinit()
    if self.sd:
      self.sd.deinit()
    if self.bufstore:
      self.bufstore.deinit()
    if self.animator:
      self.animator.deinit()
  
  def loop(self) -> None:
    self.animator.run()
    self.leds.run()
    cmdstr = self.commander.read()
    if not cmdstr:
      return
    self.leds.act.flash()
    print(f'{cmdstr=}')
    try:
      cmd = self.commander.parse(cmdstr)
      print(f'{cmd=}')
      self.do(cmd)
    except Exception as err:
      traceback.print_exception(err)
      self.leds.err.flash()
  
  def do(self, cmd: Command) -> None:
    what, verb, quantity = cmd
    action = (what, verb)
    if action not in terms.CODES:
      raise ValueError(action)
    if what not in ('brightness', 'speed', 'func_noop'):
      self.animator.clear()
    if what in self.changer.whats:
      getattr(self.changer, what)(verb, quantity)
    elif what == 'speed':
      self.animator.speed_change(verb, quantity)
    elif what == 'buffer':
      if not self.bufstore.action(verb, quantity):
        self.leds.err.flash()
      if verb == 'restore':
        self.changer.selected['hue'] = None
    elif verb == 'run':
      if what == 'func_draw':
        self.pixels.show()
      elif what == 'func_noop':
        pass
      elif what in self.animator.routines:
        if quantity is not None:
          self.animator.speed = quantity
        getattr(self.animator, what)()
      else:
        raise ValueError(action)
    else:
      raise ValueError(action)

app = App()

del(App)
