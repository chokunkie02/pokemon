import requests, json

prompt = {
    "model": "qwen2.5:3b",
    "prompt": "Current Game State:\n{\n  \"turn_number\": 2,\n  \"current_turn\": \"Goopy AI\",\n  \"phase\": \"main\",\n  \"my_state\": {\n    \"name\": \"Goopy AI\",\n    \"energy_zone\": 1,\n    \"active_pokemon\": {\"name\": \"Charmander\", \"current_hp\": 60, \"attached_energy\": []},\n    \"bench\": [],\n    \"hand_details\": [{\"id\": \"E_01\", \"category\": \"energy\"}]\n  },\n  \"opponent_state\": {\n    \"active_pokemon\": {\"name\": \"Squirtle\", \"current_hp\": 60}\n  },\n  \"legal_actions\": [\n    {\"endpoint\": \"/api/action/attach_energy\", \"payload\": {\"target_position\": \"active\"}, \"hint\": \"Powers up active\"},\n    {\"endpoint\": \"/api/action/end_turn\", \"payload\": {}, \"hint\": \"Ends turn\"}\n  ]\n}\n\nWhat is your next action?",
    "system": "You are 'Goopy AI'.\nYou MUST structure your JSON exactly like this, processing your thoughts in order in Thai:\n{\n  \"turn_analysis\": \"ข้อมูลสถานการณ์ปัจจุบัน เลือดเป็นยังไง ใครได้เปรียบ (ภาษาไทย)\",\n  \"long_term_goal\": \"เป้าหมายหลักในเทิร์นนี้คืออะไร? (ภาษาไทย)\",\n  \"risk_evaluation\": \"ความเสี่ยงมีอะไรบ้าง? (ภาษาไทย)\",\n  \"final_decision_reasoning\": \"สรุปว่าทำไมถึงเลือกเจาะจงทำ Action นี้ในเทิร์นนี้ (ภาษาไทย)\",\n  \"endpoint\": \"The exact API endpoint from the chosen legal action\",\n  \"payload\": {\n    \"player_name\": \"Goopy AI\",\n    \"card_id\": \"...\" \n  }\n}",
    "format": "json",
    "stream": False,
    "options": {"temperature": 0.1}
}

try:
    res = requests.post("http://localhost:11434/api/generate", json=prompt)
    print(res.json().get('response', 'No response field'))
except Exception as e:
    print(f"Error: {e}")
