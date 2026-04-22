#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Read the file
with open('engine/spatial_engine.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find and remove the misplaced add_log lines that are broken
# These lines should not be in the add_log method
lines_to_remove = [
    '                    self.add_log(LogCategoryEnum.ECONOMY, f"🛒 {agent.name} built a cart!")',
    '                    self.add_log(LogCategoryEnum.ECONOMY, f"🐴 {agent.name} tamed a horse!")',
    '                return',
]

for line in lines_to_remove:
    if line in content:
        content = content.replace(line + '\n\n', '')
        content = content.replace(line + '\n', '')

# Also fix the broken structure in add_log method
old_broken = '''        if isinstance(category, str):

            category = LogCategoryEnum(category)



        # Prevent immediate repeated log spam for identical messages.

        if self.logs:

            last = self.logs[-1]

                return



        # Prevent the same exact message from repeating too often across ticks.

        last_tick = self.log_signature_last_tick.get(signature, -9999)'''

new_fixed = '''        if isinstance(category, str):
            category = LogCategoryEnum(category)

        # Prevent immediate repeated log spam for identical messages.
        if self.logs:
            last = self.logs[-1]
            if last.message == msg and self.tick - last.tick < LOG_DUPLICATE_COOLDOWN:
                return

        # Prevent the same exact message from repeating too often across ticks.
        signature = f"{category}:{msg}"
        last_tick = self.log_signature_last_tick.get(signature, -9999)'''

if old_broken in content:
    content = content.replace(old_broken, new_fixed)
    print("Fixed broken add_log method structure")
else:
    print("Pattern not found exactly, attempting alternative fixes...")

# Write back
with open('engine/spatial_engine.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("File restored")
