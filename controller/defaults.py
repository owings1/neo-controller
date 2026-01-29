# Runtime Configuration

num_pixels = 7
pixel_order = 'BRG'
num_presets = 6
presets_subdir = 'buffers'
speeds = range(2, 0x82, 2)

# Default Settings

brightness_scale = 0x40
initial_brightness = brightness_scale // 5
initial_color = 0xffffff

# Serial Configuration

serial_enabled = True
baudrate = 115200
serial_timeout = 0.125

# Circuit Configuration

sd_enabled = True
data_pin = 'D2'
sd_cs_pin = 'D3'
