from __future__ import annotations

import traceback

import board
import busio
from classes import *
from neopixel import NeoPixel
from utils import settings

animator: Animator|None = None
bufstore: BufStore|None = None
commander: Commander|None = None
leds: ActLeds|None = None
pixels: NeoPixel|None = None
sd: SdReader|None = None
serial: busio.UART|None = None

def main() -> None:
  try:
    init()
    while True:
      loop()
  finally:
    deinit()

def init() -> None:
  global animator, bufstore, commander, leds, pixels, sd, serial
  pixels = NeoPixel(
    getattr(board, settings.data_pin),
    settings.num_pixels,
    brightness=settings.initial_brightness / settings.brightness_scale,
    auto_write=False,
    pixel_order=settings.pixel_order)
  sd = SdReader(getattr(board, settings.sd_cs_pin))
  sd.enabled = settings.sd_enabled
  sd.remount()
  bufstore = BufStore(pixels, sd, 6)
  bufstore.fallback_color = settings.initial_color
  animator = Animator(pixels, bufstore)
  serial = busio.UART(
    None,
    board.RX,
    baudrate=settings.baudrate,
    timeout=settings.serial_timeout)
  leds = ActLeds.frompins(board.LED_GREEN, board.LED_BLUE)
  commander = Commander(serial, pixels, bufstore, animator, leds)
  bufstore.restore(0)

def deinit() -> None:
  if commander:
    commander.deinit()
  if serial:
    serial.deinit()
  if pixels:
    pixels.deinit()
  if leds:
    leds.deinit()
  if sd:
    sd.deinit()
  if bufstore:
    bufstore.deinit()
  if animator:
    animator.deinit()

def loop() -> None:
  cmdstr = commander.read()
  if not cmdstr:
    animator.run()
    leds.run()
    return
  leds.act.flash()
  print(f'{cmdstr=}')
  try:
    cmd = commander.parse(cmdstr)
    print(f'{cmd=}')
    if cmd[0] != 'brightness':
      animator.clear()
    commander.do(*cmd)
  except Exception as err:
    traceback.print_exception(err)
    leds.err.flash()

if __name__ == '__main__':
  main()
