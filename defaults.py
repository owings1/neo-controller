# Pixels settings
num_pixels = 82
pixel_order = 'GRB'
data_pin = 'SPI'

# Brightness settings
brightness_scale = 0x20
initial_brightness = brightness_scale // 5

# Animation settings
speeds = range(0x100, 0, -0x8)
initial_speed = len(speeds) // 2 - 1
initial_routine = 'wheel_loop'
min_micros_interval = 700
transition_steps = 0x80
rando_fillchance = 0.2

# Button settings
buttons_enabled = True
buttons_reversed = False
buttons_long_duration_ms = 1_000
b0_pin = 'D6'
b1_pin = 'D5'
b2_pin = 'D4'

# Rotary settings
rotary_enabled = False
rotary_int_pin = 'D3'
rotary_address = 0x30
rotary_reverse = False
rotary_antibounce_period = 25
rotary_double_push_period = 50

# Other settings
idle_ms = 10_000