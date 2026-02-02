from __future__ import annotations

import traceback

import board
import busio
from classes import *
from neopixel import NeoPixel
from utils import settings

import terms

class App:
  animator: Animator|None = None
  bufstore: BufStore|None = None
  changer: Changer|None = None
  commander: Commander|None = None
  leds: ActLeds|None = None
  pixels: NeoPixel|None = None
  sd: SdReader|None = None
  serial: busio.UART|None = None

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
      f'on data pin {settings.data_pin} '
      f'{initial_brightness=}')
    self.pixels = NeoPixel(
      getattr(board, settings.data_pin),
      settings.num_pixels,
      brightness=initial_brightness,
      auto_write=False,
      pixel_order=settings.pixel_order)
    self.sd = SdReader(board.SPI(), getattr(board, settings.sd_cs_pin))
    self.bufstore = BufStore(self.pixels, self.sd, settings.presets_subdir, settings.num_presets)
    try:
      import custom
    except ImportError:
      custom = None
      print(f'No custom module')
    else:
      print(f'Imported custom module')
    self.animator = Animator(self.pixels, self.bufstore, custom)
    self.leds = ActLeds.frompins(board.LED_GREEN, board.LED_BLUE)
    if settings.serial_enabled:
      print(f'Initializing serial')
      self.serial = busio.UART(
        None,
        board.RX,
        baudrate=settings.baudrate,
        timeout=settings.serial_timeout)
      self.commander = Commander(self.serial, self.leds)
    else:
      print(f'Serial disabled')
    self.changer = Changer(self.pixels)
    self.bufstore.onreadstart = self.leds.act.on
    self.bufstore.onreadstop = self.leds.act.off
    if settings.sd_enabled:
      print(f'Attempting to mount SD')
      self.sd.remount()
    else:
      print('SD disabled')
    self.animator.speed = len(settings.speeds) - 1
    self.animator.anim_buffers_loop()
    # print(f'Restoring buf 0')
    # self.bufstore.restore(0)
  
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
    cmdstr = self.commander and self.commander.read()
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
    elif what == 'bufstore':
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

if __name__ == '__main__':
  app.main()
