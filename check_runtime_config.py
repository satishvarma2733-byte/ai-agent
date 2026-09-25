import urllib.request, json
with urllib.request.urlopen('http://localhost:8000/api/config', timeout=8) as r:
    config = json.loads(r.read())
    keys = ['gemini_live_voice', 'gemini_live_model', 'gemini_live_temperature', 'lang_preset', 'max_turns']
    print("=== LIVE RUNTIME CONFIG ===")
    for k in keys:
        print(f"  {k}: {config.get(k)}")
    print(f"  first_line: {str(config.get('first_line',''))[:80]}...")
    print(f"  agent_instructions: {str(config.get('agent_instructions',''))[:100]}...")
