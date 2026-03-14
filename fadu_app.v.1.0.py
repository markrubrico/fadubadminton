import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json
from datetime import datetime
from google import genai  # Official 2026 SDK

# ==========================================
# ⚙️ CONFIGURATION & SEEDING
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

# Load Secrets from Streamlit
try:
    BRIDGE_URL = st.secrets["BRIDGE_URL"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    BRIDGE_URL = "NOT_CONFIGURED"
    GEMINI_API_KEY = "NOT_CONFIGURED"

# ==========================================
# ✨ AI SANITIZER (GEMINI 2.0 FLASH - FREE TIER)
# ==========================================
def ai_sanitize_logs(raw_input):
    if GEMINI_API_KEY == "NOT_CONFIGURED":
        return "ERROR: Missing API Key in Secrets."
    
    try:
        # Initialize Client
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        prompt = f"""
        You are the Master Data Parser for the Fadu Badminton League.
        TASK: Convert messy, conversational logs into programmatic W/L format.
        
        RULES:
        1. OUTPUT FORMAT: 'Game X: W: P1, P2 | L: P3, P4'
        2. LOGIC: Reconcile all names and fix typos based on common sense.
        3. DATES: Keep lines like '20-Feb' exactly as they are.
        4. NO CHAT: Return ONLY the cleaned logs.
        
        INPUT:
        {raw_input}
        """
        
        # Switched to 'gemini-2.0-flash' which is the stable 2026 Free Tier model
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"temperature": 0.1}
        )
        return response.text.strip()
    except Exception as e:
        return f"AI Error: {str(e)}"

# ==========================================
# 🧠 DYNAMIC MMR ENGINE v5.1 (FULL LOGIC)
# ==========================================
class FaduMMREngine:
    def __init__(self, elite_list):
        self.elite_list = [n.strip().lower() for n in elite_list]
        self.players = {}

    def get_player(self, name):
        n_clean = name.strip()
        n_lower = n_clean.lower()
        if n_lower not in self.players:
            start_mmr = 1500 if n_lower in self.elite_list else 1000
            self.players[n_lower] = {
                'display_name': n_clean, 'mmr': start_mmr, 'peak': start_mmr, 
                'wins': 0, 'losses': 0, 'total_opp_mmr': 0, 'total_partner_mmr_delta': 0, 
                'mmr_start': start_mmr, 'session_w': 0, 'session_l': 0, 
                'last_idx': -1, 'active': False, 'win_streak': 0
            }
        return n_lower

    def generate_remark(self, p, apd, aod, thresh, rank):
        if rank == 1: return "The Final Boss. Absolute League Dominance."
        if p['win_streak'] >= 3: return f"Heat Check! {p['win_streak']} Game Win Streak."
        if apd < -250: return "The Anchor. Carrying the partnership weight."
        if aod > 1650: return "Iron Man. Battling the league heavyweights."
        if p['session_l'] >= 3: return "Rough Night. The grind continues."
        return "Pure Hustle. A consistent force."

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
                    w_list = [n.strip() for n in p[0].split('W:')[1].split(',')]
                    l_list = [n.strip() for n in p[1].split('L:')[1].split(',')]
                    logs.append({'date': date, 'W': w_list, 'L': l_list})
                except: continue
        
        if not logs: return pd.DataFrame()
        dates = list(dict.fromkeys([l['date'] for l in logs]))
        
        for idx, d in enumerate(dates):
            is_last = (idx == len(dates) - 1)
            for p in self.players.values(): p['active'], p['session_w'], p['session_l'] = False, 0, 0
            
            for g in [x for x in logs if x['date'] == d]:
                wk = [self.get_player(n) for n in g['W']]
                lk = [self.get_player(n) for n in g['L']]
                active_mmrs = [p['mmr'] for p in self.players.values()]
                thresh = np.percentile(active_mmrs, 80) if active_mmrs else 1500

                for i, k in enumerate(wk):
                    w = self.players[k]
                    if not w['active']: w['mmr_start'], w['active'] = w['mmr'], True
                    opp_max = max([self.players[lk_id]['mmr'] for lk_id in lk]) if lk else 1000
                    bonus = min((opp_max - w['mmr']) * 0.25, 80) if w['mmr'] < 1349 and (opp_max - w['mmr']) > 300 else 0
                    w['mmr'] += (40 + bonus); w['wins'] += 1; w['session_w'] += 1; w['win_streak'] += 1; w['peak'] = max(w['peak'], w['mmr'])
                    w['total_opp_mmr'] += (sum([self.players[lk_id]['mmr'] for lk_id in lk]) / 2)
                    w['total_partner_mmr_delta'] += (self.players[wk[1-i]]['mmr'] - w['mmr'])

                for i, k in enumerate(lk):
                    l = self.players[k]; partner = self.players[lk[1-i]]
                    if not l['active']: l['mmr_start'], l['active'] = l['mmr'], True
                    loss = 10 if (l['wins'] + l['losses']) < 5 else 20
                    gap = l['mmr'] - partner['mmr']
                    if (l['mmr'] >= thresh and gap >= 150) or (partner['mmr'] >= thresh and (partner['mmr'] - l['mmr']) >= 150): loss = 16
                    l['mmr'] -= loss; l['losses'] += 1; l['session_l'] += 1; l['win_streak'] = 0
                    l['total_opp_mmr'] += (sum([self.players[wk_id]['mmr'] for wk_id in wk]) / 2)
                    l['total_partner_mmr_delta'] += (partner['mmr'] - l['mmr'])

            if not is_last:
                for p in self.players.values():
                    if p['active']: p['last_idx'] = idx

        res = []
        for k, p in self.players.items():
            total = p['wins'] + p['losses']
            if total == 0: continue
            aod = round(p['total_opp_mmr'] / total)
            apd = round(p['total_partner_mmr_delta'] / total)
            res.append({
                "Rank": 0, "Player": p['display_name'], 
                "Tier": next(t for t, v in TIERS.items() if p['mmr'] >= v), "MMR": round(p['mmr']),
                "Peak": round(p['peak']), "Session +/-": round(p['mmr'] - p['mmr_start']) if p['active'] else 0,
                "Avg Opponent MMR": aod, "Avg Partner Delta": apd,
                "Record": f"{p['wins']}-{p['losses']}", "Session": f"{p['session_w']}-{p['session_l']}", "w": p['wins'], "key": k
            })
        
        df = pd.DataFrame(res).sort_values(by=["MMR", "w"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        df["Power Remarks"] = df.apply(lambda r: self.generate_remark(self.players[r['key']], r['Avg Partner Delta'], r['Avg Opponent MMR'], thresh, r['Rank']), axis=1)
        return df.drop(columns=['w', 'key'])

# ==========================================
# 🎨 STREAMLIT DASHBOARD UI
# ==========================================
st.set_page_config(page_title="Fadu MMR v4.0", layout="wide", page_icon="🏸")
if 'logs' not in st.session_state: st.session_state.logs = ""

with st.sidebar:
    st.title("🏸 Fadu Ops")
    st.success("Sheets: 🟢 Online") if BRIDGE_URL != "NOT_CONFIGURED" else st.error("Sheets: 🔴 Offline")
    st.success("Gemini 2.0 Flash: 🟢 Connected") if GEMINI_API_KEY != "NOT_CONFIGURED" else st.error("AI: 🔴 No Key")
    st.divider()
    st.caption("v4.0 | March 2026 Free Tier")

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
                st.success("Synced to Sheets Registry!")