import board
import neopixel
import time


# NeoPixel strip connected on D4
NUMPIXELS = 8
neopixels = neopixel.NeoPixel(
    board.D6,
    NUMPIXELS,
    brightness=0.2,
    # auto_write=False,
    pixel_order="BRG",
    )


# for p in range(NUMPIXELS):
#     neopixels[p] = 0, 255, 0
# neopixels.show()
for p in range(NUMPIXELS):
    neopixels[0] = 255, 0, 0
    neopixels.show()
    time.sleep(1)

# while True:
#     for p in range(NUMPIXELS):
#         if neopixels[p][0]:
#             neopixels[p] = 0, 255, 0
#         else:
#             neopixels[p] = 255, 0, 0
#         neopixels.show()
#         time.sleep(1)
