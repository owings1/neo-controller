actions = {
  'a': 'brightness_set',
  'b': 'brightness_plus',
  'c': 'brightness_minus',
  'd': 'brightness_clear',
  'e': 'red_set',
  'f': 'red_plus',
  'g': 'red_minus',
  'h': 'red_clear',
  'i': 'green_set',
  'j': 'green_plus',
  'k': 'green_minus',
  'l': 'green_clear',
  'm': 'blue_set',
  'n': 'blue_plus',
  'o': 'blue_minus',
  'p': 'blue_clear',
  'q': 'white_set',
  'r': 'white_plus',
  's': 'white_minus',
  't': 'white_clear',
  'u': 'pixel_set',
  'v': 'pixel_plus',
  'w': 'pixel_minus',
  'x': 'pixel_clear',
  'y': 'func_draw',
  'z': 'func_save',
}

codes = dict(map(reversed, actions.items()))
