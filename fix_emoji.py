# -*- coding: utf-8 -*-

# Read file as binary
with open('engine/spatial_engine.py', 'rb') as f:
    data = f.read()

# Fix the corrupted emoji bytes
# The corrupted ring emoji bytes: \xc3\xb0\xc5\xb8\xe2\x80\x99\xe2\x80\x99
# The correct ring emoji bytes: \xf0\x9f\x92\x8d
data = data.replace(b'\xc3\xb0\xc5\xb8\xe2\x80\x99\xe2\x80\x99', b'\xf0\x9f\x92\x8d')

# Write back
with open('engine/spatial_engine.py', 'wb') as f:
    f.write(data)

print('✓ Fixed married icon emoji in spatial_engine.py!')
