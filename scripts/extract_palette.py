from PIL import Image
import sys

import os

# Try multiple possible paths
candidates = [
    'static/images/bwlogo.png',
    os.path.join('app','static','images','bwlogo.png'),
]
path = None
for p in candidates:
    if os.path.exists(p):
        path = p
        break
if path is None:
    print('ERROR: file not found in any candidate paths:')
    for p in candidates:
        print(' -', p)
    sys.exit(1)
print('Found logo at:', path)
img = Image.open(path).convert('RGBA')

# Resize to speed up
img_small = img.resize((150, 150))

# Get colors
pixels = list(img_small.getdata())
# Filter out transparent and near-white pixels
filtered = [p for p in pixels if p[3] > 40 and not (p[0] > 240 and p[1] > 240 and p[2] > 240)]

from collections import Counter
cnt = Counter(filtered)
most = cnt.most_common(6)

# Convert to hex
hex_colors = []
for (r,g,b,a), count in most:
    hex_colors.append('#{:02x}{:02x}{:02x}'.format(r,g,b))

print(' '.join(hex_colors))
