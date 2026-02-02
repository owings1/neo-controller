# Runtime Configuration
num_pixels = 82
pixel_order = 'GRB'
initial_speed = 0xff
# initial_routine = 'red_loop'
initial_routine = 'wheel_loop'

# Default Settings
brightness_scale = 0x10
initial_brightness = brightness_scale // 5
speeds = range(0x100, 0, -0x10)
min_micros_interval = 700
transition_steps = 0x80
rando_fillchance = 0.2
# initial_color = 0xffffff

# Circuit Configuration
data_pin = 'SPI'
b0_pin = 'D6'
b1_pin = 'D5'
b2_pin = 'D4'
