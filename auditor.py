import streamlit as st
import requests

def ai_audit_session(raw_input, established_players):
    try: api_key = st.secrets["GROQ_API_KEY"]
    except: return "ERROR: No GROQ_API_KEY found."
    
    blocks = raw_input.strip().split('\n\n')
    active_session = blocks[-1] if blocks else raw_input
    
    prompt = f"""
    [Auditor Mode] Focus only on ACTIVE DATA. Cross-ref Roster: {established_players}.
    1. Check phonetic typos. 2. Flag duplicate dates. 3. New player debut identification.
    Output: Markdown Table.
    """
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": f"{prompt}\n\nACTIVE DATA:\n{active_session}"}],
        "temperature": 0.0
    }
    
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json=payload)
        return r.json()['choices'][0]['message']['content'].strip()
    except Exception as e: return f"Audit Error: {str(e)}"