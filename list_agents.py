import urllib.request, json
with urllib.request.urlopen('http://localhost:8000/api/agents', timeout=8) as r:
    agents = json.loads(r.read())
    print(f'Total agents: {len(agents)}')
    for a in agents:
        print(f"  ID: {a['id']} | [{a['status']}] {a['name']} | Voice: {a['voice']} | Model: {a['model'][:30]}")
