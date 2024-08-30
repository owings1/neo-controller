from __future__ import annotations

import traceback

import board
import sdcardio
import storage
from microcontroller import Pin


class SDcard:

  sd: sdcardio.SDCard|None
  vfs: storage.VfsFat|None

  def __init__(
    self,
    cs: Pin,
    *,
    path: str = '/sd',
    enabled: bool = True
  ) -> None:
    self.cs = cs
    self.path = path
    self.enabled = enabled
    self.sd = None
    self.vfs = None

  @property
  def checkfile(self) -> str:
    return f'{self.path}/.mountcheck'

  def check(self) -> bool:
    if self.sd:
      try:
        open(self.checkfile).close()
        return True
      except OSError:
        pass
    return self.init()

  def init(self) -> bool:
    if not self.enabled:
      return False
    self.deinit()
    try:
      self.sd = sdcardio.SDCard(board.SPI(), self.cs)
      self.vfs = storage.VfsFat(self.sd)
      storage.mount(self.vfs, self.path)
      open(self.checkfile, 'w').close()
    except OSError as err:
      traceback.print_exception(err)
      self.deinit()
      return False
    return True

  def deinit(self) -> None:
    if self.sd:
      try:
        storage.umount(self.path)
      except OSError:
        pass
      self.sd.deinit()
      self.sd = None
      self.vfs = None

  def mkdirp(self, path: str) -> bool:
    if not path:
      return ValueError(path)
    if not self.check():
      return False
    try:
      stat = self.vfs.stat(path)
    except OSError as err:
      if err.errno != 2:
        traceback.print_exception(err)
        return False
    else:
      if (stat[0] & 0x4000) == 0x4000:
        return True
      traceback.print_exception(Exception(f'{path} not a directory {stat=}'))
      return False
    nodes = path.split('/')
    nodes.reverse()
    try:
      cur = nodes.pop()
      self.vfs.mkdir(cur)
      for node in nodes:
        cur += f'/{node}'
        self.vfs.mkdir(cur)
    except OSError as err:
      traceback.print_exception(err)
      return False
    return True
