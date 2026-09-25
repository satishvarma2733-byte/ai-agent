filepath = r"c:\Users\abhin\Desktop\ai voice agent\Inbound-Agent\agent_backend.py"
with open(filepath, "r", encoding="utf-8") as f:
    code = f.read()

import re
matches = re.findall(r'.{0,100}recording.{0,100}', code, re.IGNORECASE)
print("Recording occurrences:", len(matches))
for m in matches[:10]:
    print("-", m.strip())
