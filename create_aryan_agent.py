import urllib.request, json, urllib.error, sys

BASE = 'http://localhost:8000'

aryan = {
  'name': 'Aryan - AVN AI Inbound Receptionist',
  'status': 'active',
  'voice': 'Puck',
  'model': 'gemini-2.0-flash-live-001',
  'description': 'AI voice agent for AVN AI. Handles inbound calls, qualifies leads, books consultations. Gemini 2.0 Flash Live with multilingual Hinglish support.',
  'tags': ['inbound', 'avn-ai', 'sales', 'multilingual', 'kb-enabled'],
  'instructions': (
    "You are Aryan, a friendly and professional AI receptionist for AVN AI - a company "
    "that helps businesses automate operations using AI voice agents, CRM automation, and workflow intelligence.\n\n"
    "Your primary goals:\n"
    "1. Warmly greet the caller and understand their business type\n"
    "2. Qualify their interest in AI automation (team size, pain points, budget awareness)\n"
    "3. Explain AVN AI key offerings: AI inbound/outbound calling, Voice CRM, Workflow automation\n"
    "4. Invite them to book a free 30-minute consultation session\n"
    "5. Collect name, phone, preferred time slot\n"
    "6. If technical questions arise, refer to Knowledge Base\n\n"
    "Tone: Conversational, warm, consultative. Mix Hindi and English naturally (Hinglish) for Indian callers.\n"
    "Never be pushy. Always listen first, then suggest.\n"
    "Max call duration: 5 minutes. Always end with a next step (booking or callback)."
  ),
  'greeting': 'Namaste! This is Aryan from AVN AI - we help businesses automate with AI. Hmm, may I ask what kind of business you run?',
  'language': 'hi',
  'temperature': 0.8,
  'max_call_duration': 300,
  'fallback_phone': '',
  'working_hours_start': '09:00',
  'working_hours_end': '21:00',
  'working_days': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
  'calls_today': 0,
  'calls_total': 0,
  'avg_duration': 0,
  'success_rate': 0,
  'last_active': None,
}

def do_post(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        method='POST',
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

print("=== Step 1: Creating Aryan Agent ===")
try:
    result = do_post(f'{BASE}/api/agents', aryan)
    agent_id = result.get('agent', {}).get('id', 'unknown')
    print(f"Status: {result.get('status')}")
    print(f"Agent ID: {agent_id}")
    print(f"Agent Name: {result.get('agent', {}).get('name')}")
except Exception as e:
    print(f"FAILED to create agent: {e}")
    sys.exit(1)

print()
print("=== Step 2: Deploying to Live Runtime Config ===")
config_patch = {
    'gemini_live_voice': 'Puck',
    'gemini_live_model': 'gemini-2.0-flash-live-001',
    'gemini_live_temperature': 0.8,
    'gemini_live_language': '',
    'first_line': 'Namaste! This is Aryan from AVN AI - we help businesses automate with AI. Hmm, may I ask what kind of business you run?',
    'agent_instructions': aryan['instructions'],
    'max_turns': 15,
    'lang_preset': 'multilingual',
}
try:
    cfg_result = do_post(f'{BASE}/api/config', config_patch)
    cfg = cfg_result.get('config', {})
    print(f"Config Status: {cfg_result.get('status')}")
    print(f"Voice set to: {cfg.get('gemini_live_voice')}")
    print(f"Model set to: {cfg.get('gemini_live_model')}")
    print(f"Lang preset: {cfg.get('lang_preset')}")
    print(f"First line: {str(cfg.get('first_line', ''))[:70]}...")
except Exception as e:
    print(f"FAILED to update config: {e}")
    sys.exit(1)

print()
print("SUCCESS: Aryan agent created and deployed to live runtime!")
print(f"Agent ID: {agent_id}")
