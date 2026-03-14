import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json
from datetime import datetime
from google import genai  # Latest 2026 SDK

# ==========================================
# ⚙️ LEAGUE CONFIGURATION & SEEDING
# ==========================================
# Veterans receive a starting seed of 1500 MMR.
# New players discovered in logs start at 1000 MMR.
ELITE_START = [
    "Kenmore", "Lance", "Sam", "Jerome", "Pacs", "VJ", "Luke", 
    "Kent", "Ivan", "Efren", "Jayson", "Allen", "Bombi", "AJ"
]

TIERS = {
    "Mythical Glory": 2750,
    "Mythic": 2300,
    "Legend": 1900,
    "Epic": 1650,
    "Grandmaster": 1350,
    "Master": 0
}

# Load Secrets
try:
    BRIDGE_URL = st.secrets["BRIDGE_URL"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    BRIDGE_URL = "NOT_CONFIGURED"
    GEMINI_API_KEY = "NOT_CONFIGURED"

# ==========================================
# ✨ 2026 AI SANITIZER (GEMINI 3 FLASH)
# ==========================================
def ai_sanitize_logs(raw_input):
    if GEMINI_API_KEY == "NOT_CONFIGURED":
        return "ERROR: Missing API Key in Secrets."
    
    try:
        # Initialize the 2026 GenAI Client
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = f"""
        You are the Master Data Parser for the Fadu Badminton League.
        TASK: Convert messy, conversational logs into programmatic W/L format.
        
        RULES:
        1. OUTPUT FORMAT: 'Game X: W: P1, P2 | L: P3, P4'
        2. LOGIC: Correct names based on the Roster: {ELITE_START}
        3. DATES: Keep lines like '20-Feb' exactly as they are.
        4. NO CHAT: Return ONLY the cleaned logs.
        
        INPUT:
        {raw_input}
        """
        
        # Using 2026 'gemini-3-flash' model with 'medium' thinking
        response = client.models.generate_content(
            model="gemini-3-flash",
            contents=prompt,
            config={
                "thinking_level": "medium", # 2026 Feature
                "temperature": 0.1
            }
        )
        return response.text.strip()
    except Exception as e:
        return f"AI Error: {str(e)}"

# ==========================================
# 🧠 DYNAMIC MMR ENGINE v5.0 (FULL LOGIC)
# ==========================================
class FaduMMREngine:
    def __init__(self, elite_list):
        self.elite_list = [n.strip().lower() for n in elite_list]
        self.players = {}

    def get_player(self, name):
        n_clean = name.strip()
        n_lower = n_clean.lower()
        if n_lower not in self.players:
            # Dynamic Headstart Seeding
            start_mmr = 1500 if n_lower in self.elite_list else 1000
            self.players[n_lower] = {
                'display_name': n_clean, 'mmr': start_mmr, 'peak': start_mmr, 
                'wins': 0, 'losses': 0, 'total_opp_mmr': 0, 'total_partner_mmr_delta': 0, 
                'mmr_start': start_mmr, 'session_w': 0, 'session_l': 0, 
                'last_idx': -1, 'active': False, 'streak': 0
            }
        return n_lower

    def generate_remark(self, p, apd, aod, thresh, rank):
        if rank == 1: return "The Final Boss. Absolute League Dominance."
        if p['streak'] >= 3: return f"Heat Check! {p['streak']} Game Win Streak."
        if apd < -250: return "The Anchor. Carrying the partnership weight."
        if aod > 1650: return "Iron Man. Battling the league heavyweights."
        if p['session_l'] >= 3: return "Rough Night. The grind continues."
        return "Pure Hustle. A consistent force."

    def simulate(self, text):
        # 1. Parsing
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
        
        # 2. Iteration
        for idx, d in enumerate(dates):
            is_last = (idx == len(dates) - 1)
            for p in self.players.values(): p['active'], p['session_w'], p['session_l'] = False, 0, 0
            
            for g in [x for x in logs if x['date'] == d]:
                wk = [self.get_player(n) for n in g['W']]
                lk = [self.get_player(n) for n in g['L']]
                thresh = np.percentile([p['mmr'] for p in self.players.values()], 80) if self.players else 1500

                # Winner Path
                for i, k in enumerate(wk):
                    w = self.players[k]
                    if not w['active']: w['mmr_start'], w['active'] = w['mmr'], True
                    bonus = min((max([self.players[x]['mmr'] for x in lk]) - w['mmr']) * 0.25, 80) if w['mmr'] < 1349 else 0
                    w['mmr'] += (40 + bonus); w['wins'] += 1; w['session_w'] += 1; w['streak'] += 1; w['peak'] = max(w['peak'], w['mmr'])
                    w['total_opp_mmr'] += (sum([self.players[x]['mmr'] for x in lk]) / 2)
                    w['total_partner_mmr_delta'] += (self.players[wk[1-i]]['mmr'] - w['mmr'])

                # Loser Path (Shields)
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

        # 3. Leaderboard Generation
        res = []
        for k, p in self.players.items():
            total = p['wins'] + p['losses']
            if total == 0: continue
            res.append({
                "Rank": 0, "Player": p['display_name'], 
                "Tier": next(t for t, v in TIERS.items() if p['mmr'] >= v), "MMR": round(p['mmr']),
                "Peak": round(p['peak']), "Session +/-": round(p['mmr'] - p['mmr_start']) if p['active'] else 0,
                "Avg Opponent MMR": round(p['total_opp_mmr'] / total), 
                "Avg Partner Delta": round(p['total_partner_mmr_delta'] / total),
                "Record": f"{p['wins']}-{p['losses']}", "Session": f"{p['session_w']}-{p['session_l']}", "w": p['wins'], "key": k
            })
        
        df = pd.DataFrame(res).sort_values(by=["MMR", "w"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        df["Power Remarks"] = df.apply(lambda r: self.generate_remark(self.players[r['key']], r['Avg Partner Delta'], r['Avg Opponent MMR'], thresh, r['Rank']), axis=1)
        return df.drop(columns=['w', 'key'])

# ==========================================
# 🎨 UI & DASHBOARD
# ==========================================
st.set_page_config(page_title="Fadu MMR v3.0", layout="wide", page_icon="🏸")
if 'logs' not in st.session_state: st.session_state.logs = ""

with st.sidebar:
    st.title("🏸 Fadu Ops")
    if BRIDGE_URL != "NOT_CONFIGURED": st.success("Registry: 🟢 Online")
    else: st.error("Registry: 🔴 Offline")
    if GEMINI_API_KEY != "NOT_CONFIGURED": st.success("Gemini 3 Flash: 🟢 Connected")
    else: st.error("AI: 🔴 No Key")
    st.divider()
    st.caption("v3.0 | March 2026 Protocol")

st.title("🏸 Fadu Badminton Power Rankings")
input_area = st.text_area("Match Logs Input:", value=st.session_state.logs, height=350)

c1, c2, _ = st.columns([1, 1, 4])
with c1:
    if st.button("✨ AI Sanitize", type="secondary", use_container_width=True):
        with st.spinner("AI thinking..."):
            st.session_state.logs = ai_sanitize_logs(input_area)
            st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        with st.spinner("Processing Stat Trajectories..."):
            engine = FaduMMREngine(ELITE_START)
            leaderboard = engine.simulate(input_area)
            st.dataframe(leaderboard, use_container_width=True, hide_index=True)
            if BRIDGE_URL != "NOT_CONFIGURED":
                requests.post(BRIDGE_URL, json={"target": "Registry", "headers": leaderboard.columns.tolist(), "values": leaderboard.values.tolist()})
                st.success("Synced to Registry!")