#!/usr/bin/env python3

# Fix spatial_engine.py by removing broken lines
with open('engine/spatial_engine.py', 'rb') as f:
    content = f.read()

# Remove the misplaced emoji add_log lines by replacing them with empty
# Cart emoji add_log
content = content.replace(b'                    self.add_log(LogCategoryEnum.ECONOMY, f"\xf0\x9f\x9b\x92 {agent.name} built a cart!")\r\n\r\n', b'')
content = content.replace(b'                    self.add_log(LogCategoryEnum.ECONOMY, f"\xf0\x9f\x9b\x92 {agent.name} built a cart!")\n\n', b'')

# Horse emoji add_log  
content = content.replace(b'                    self.add_log(LogCategoryEnum.ECONOMY, f"\xf0\x9f\x90\xb4 {agent.name} tamed a horse!")\r\n\r\n', b'')
content = content.replace(b'                    self.add_log(LogCategoryEnum.ECONOMY, f"\xf0\x9f\x90\xb4 {agent.name} tamed a horse!")\n\n', b'')

with open('engine/spatial_engine.py', 'wb') as f:
    f.write(content)

print("Cleaned broken add_log lines")
