import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json
from datetime import datetime
import time

# ==========================================
# ⚙️ LEAGUE CONFIGURATION
# ==========================================
# VETERANS: Start at 1500 MMR. Everyone else starts at 1000.
ELITE_START = [
    "Kenmore", "Lance", "Sam", "Jerome", "Pacs", "VJ", "Luke", 
    "Kent", "Ivan", "Efren", "Jayson", "Allen", "Bombi", "AJ"
]

TIERS = {
    "Mythical Glory": 2750, "Mythic": 2300, "Legend": 1900,
    "Epic": 1650, "Grandmaster": 1350, "Master": 0
}

try:
    BRIDGE_URL = st.secrets["BRIDGE_URL"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    BRIDGE_URL = "NOT_CONFIGURED"
    GEMINI_API_KEY = "NOT_CONFIGURED"

# ==========================================
# ✨ AI SANITIZER (TRIPLE-FALLBACK SYSTEM)
# ==========================================
def ai_sanitize_logs(raw_input):
    if GEMINI_API_KEY == "NOT_CONFIGURED":
        return "ERROR: Missing API Key in Secrets."
    
    # We try 3 different endpoints because Google is inconsistent with Flash
    endpoints = [
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
        f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    ]
    
    prompt = f"""
    You are the Data Architect for Fadu Badminton. 
    TASK: Convert messy logs to 'Game X: W: P1, P2 | L: P3, P4'.
    RULES: 1. Identify winners/losers from context. 2. Map names to: {ELITE_START}. 
    3. Keep Date Headers. 4. Return ONLY cleaned logs.
    INPUT: {raw_input}
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    for url in endpoints:
        try:
            response = requests.post(url, json=payload, timeout=20)
            if response.status_code == 200:
                res_json = response.json()
                return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        except:
            continue
            
    return "AI Error: All connection attempts failed. Please check your API key permissions in Google AI Studio."

# ==========================================
# 🧠 DYNAMIC MMR ENGINE v5.0
# ==========================================
class FaduMMREngine:
    def __init__(self, elite_list):
        self.elite_list = [n.strip().lower() for n in elite_list]
        self.players = {}

    def get_player(self, name):
        n_clean = name.strip()
        n_lower = n_clean.lower()
        if n_lower not in self.players:
            start = 1500 if n_lower in self.elite_list else 1000
            self.players[n_lower] = {
                'display_name': n_clean, 'mmr': start, 'peak': start, 'wins': 0, 'losses': 0,
                'total_opp_mmr': 0, 'total_partner_mmr_delta': 0, 'mmr_start': start, 
                'session_w': 0, 'session_l': 0, 'last_idx': -1, 'active': False, 'streak': 0
            }
        return n_lower

    def generate_remark(self, p, apd, aod, thresh, rank):
        if p.get('last_idx') == -1 and p['active']: return "Rookie debut."
        if rank == 1: return "The Final Boss."
        if p['streak'] >= 3: return f"On Fire ({p['streak']} wins)!"
        if apd < -250: return "The Anchor."
        if aod > 1650: return "Iron Man."
        return "Pure Hustle."

    def simulate(self, text):
        logs = []
        date = "Unknown"
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('!!'): continue
            date_m = re.match(r'^(\d{1,2}-[A-Za-z]+)', line)
            if date_m: date = date_m.group(1)
            elif 'W:' in line:
                try:
                    p = line.split('|')
                    w = [n.strip() for n in p[0].split('W:')[1].split(',')]
                    l = [n.strip() for n in p[1].split('L:')[1].split(',')]
                    logs.append({'date': date, 'W': w, 'L': l})
                except: continue
        
        if not logs: return pd.DataFrame()
        dates = list(dict.fromkeys([l['date'] for l in logs]))
        
        for idx, d in enumerate(dates):
            is_last = (idx == len(dates) - 1)
            for p in self.players.values(): p['active'], p['session_w'], p['session_l'] = False, 0, 0
            
            for g in [x for x in logs if x['date'] == d]:
                wk = [self.get_player(n) for n in g['W']]
                lk = [self.get_player(n) for n in g['L']]
                thresh = np.percentile([p['mmr'] for p in self.players.values()], 80) if self.players else 1500

                for i, k in enumerate(wk):
                    w = self.players[k]
                    if not w['active']: w['mmr_start'], w['active'] = w['mmr'], True
                    bonus = min((max([self.players[x]['mmr'] for x in lk]) - w['mmr']) * 0.25, 80) if w['mmr'] < 1349 else 0
                    w['mmr'] += (40 + bonus); w['wins'] += 1; w['session_w'] += 1; w['streak'] += 1; w['peak'] = max(w['peak'], w['mmr'])
                    w['total_opp_mmr'] += (sum([self.players[x]['mmr'] for x in lk]) / 2)
                    w['total_partner_mmr_delta'] += (self.players[wk[1-i]]['mmr'] - w['mmr'])

                for i, k in enumerate(lk):
                    l = self.players[k]; partner = self.players[lk[1-i]]
                    if not l['active']: l['mmr_start'], l['active'] = l['mmr'], True
                    loss = 10 if (l['wins'] + l['losses']) < 5 else 20
                    gap = l['mmr'] - partner['mmr']
                    if (l['mmr'] >= thresh and gap >= 150) or (partner['mmr'] >= thresh and (partner['mmr'] - l['mmr']) >= 150): loss = 16
                    l['mmr'] -= loss; l['losses'] += 1; l['session_l'] += 1; l['streak'] = 0
                    l['total_opp_mmr'] += (sum([self.players[x]['mmr'] for x in wk]) / 2)
                    l['total_partner_mmr_delta'] += (partner['mmr'] - l['mmr'])

            if not is_last:
                for p in self.players.values():
                    if p['active']: p['last_idx'] = idx

        res = []
        for k, p in self.players.items():
            total = p['wins'] + p['losses']
            if total == 0: continue
            res.append({
                "Rank": 0, "Player": p['display_name'], "Tier": next(t for t, v in TIERS.items() if p['mmr'] >= v), "MMR": round(p['mmr']),
                "Peak": round(p['peak']), "Session +/-": round(p['mmr'] - p['mmr_start']) if p['active'] else 0,
                "Avg Opponent MMR": round(p['total_opp_mmr'] / total), "Avg Partner Delta": round(p['total_partner_mmr_delta'] / total),
                "Record": f"{p['wins']}-{p['losses']}", "Session": f"{p['session_w']}-{p['session_l']}", "w": p['wins'], "key": k
            })
        
        df = pd.DataFrame(res).sort_values(by=["MMR", "w"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        df["Power Remarks"] = df.apply(lambda r: self.generate_remark(self.players[r['key']], r['Avg Partner Delta'], r['Avg Opponent MMR'], thresh, r['Rank']), axis=1)
        return df.drop(columns=['w', 'key'])

# ==========================================
# 🎨 UI
# ==========================================
st.set_page_config(page_title="Fadu MMR v2.0", layout="wide")
if 'logs' not in st.session_state: st.session_state.logs = ""

with st.sidebar:
    st.title("🏸 Fadu Ops")
    if BRIDGE_URL != "NOT_CONFIGURED": st.success("Registry: 🟢")
    else: st.error("Registry: 🔴")
    
    if GEMINI_API_KEY != "NOT_CONFIGURED":
        st.success("AI: 🟢 READY")
    else: st.error("AI: 🔴 NO KEY")

st.title("🏸 Fadu Badminton Power Rankings")
logs_in = st.text_area("Logs:", value=st.session_state.logs, height=300)

c1, c2 = st.columns([1, 1])
with c1:
    if st.button("✨ AI Sanitize", use_container_width=True):
        with st.spinner("AI Parsing..."):
            st.session_state.logs = ai_sanitize_logs(logs_in)
            st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", use_container_width=True):
        with st.spinner("Processing..."):
            engine = FaduMMREngine(ELITE_START)
            res = engine.simulate(logs_in)
            st.dataframe(res, use_container_width=True, hide_index=True)
            if BRIDGE_URL != "NOT_CONFIGURED":
                requests.post(BRIDGE_URL, json={"target": "Registry", "headers": res.columns.tolist(), "values": res.values.tolist()})
                st.success("Synced!")