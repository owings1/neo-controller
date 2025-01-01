# Button Configuration

# how long to hold a key before repeating (milliseconds)
repeat_threshold = 1000

# how often to repeat (milliseconds)
repeat_interval = 50

layout = (
  'clear',
  'minus',
  'plus',
  'hue',
  'pixel',
  'color',
  'restore',
  'save',
  'run',
)

# Whether the pixels are upside down
reverse_pixel_dir = False

# Serial Configuration

baudrate = 115200
serial_timeout = 0.1
command_redundancy = 0

# Circuit Configuration

button_pins = (
  'D0', 'D5', 'D4',
  'D1', 'D2', 'D3',
  'D8', 'D9', 'D10',
)
