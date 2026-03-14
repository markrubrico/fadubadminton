import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json
from datetime import datetime

# ==========================================
# ⚙️ CONFIGURATION & LEAGUE SEEDS
# ==========================================
ELITE_START = [
    "Kenmore", "Lance", "Sam", "Jerome", "Pacs", "VJ", "Luke", 
    "Kent", "Ivan", "Efren", "Jayson", "Allen", "Bombi", "AJ"
]

TIERS = [
    ("Mythical Glory", 2749), ("Mythic", 2299), ("Legend", 1899),
    ("Epic", 1649), ("Grandmaster", 1349), ("Master", 0)
]

try:
    BRIDGE_URL = st.secrets["BRIDGE_URL"]
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except:
    BRIDGE_URL = "NOT_CONFIGURED"; GROQ_API_KEY = "NOT_CONFIGURED"

# ==========================================
# ✨ GROQ AI SANITIZER (FAST INFERENCE)
# ==========================================
def ai_sanitize_logs(raw_input):
    if GROQ_API_KEY == "NOT_CONFIGURED": return "ERROR: Missing GROQ_API_KEY."
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    prompt = f"Convert messy badminton logs to: 'Game X: W: P1, P2 | L: P3, P4'. Reconcile names using: {ELITE_START}. Keep Date Headers. Return ONLY the cleaned logs."
    payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": f"{prompt}\n\nINPUT:\n{raw_input}"}], "temperature": 0.1}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e: return f"AI Error: {str(e)}"

# ==========================================
# 🧠 DYNAMIC MMR ENGINE v8.0 (OPS MANUAL)
# ==========================================
class FaduMMREngine:
    def __init__(self, elite_list):
        self.elite_list = [n.strip().lower() for n in elite_list]
        self.players = {}

    def get_player(self, name, date_idx, total_dates):
        n_clean = name.strip(); n_lower = n_clean.lower()
        if n_lower not in self.players:
            start = 1500 if n_lower in self.elite_list else 1000
            self.players[n_lower] = {
                'name': n_clean, 'mmr': start, 'peak': start, 'wins': 0, 'losses': 0,
                't_opp': 0, 't_p_delta': 0, 'mmr_s': start, 's_w': 0, 's_l': 0, 
                'active': False, 'is_new': (date_idx == total_dates - 1), 'win_streak': 0
            }
        return n_lower

    def get_tier(self, mmr):
        for name, threshold in TIERS:
            if mmr > threshold: return name
        return "Master"

    def generate_remark(self, p, apd, aod, rank):
        if p['is_new']: return "Rookie debut. Welcome!"
        if rank == 1: return "The Final Boss. Absolute League Dominance."
        if p['win_streak'] >= 3: return f"Heat Check! {p['win_streak']} Win Streak."
        if apd < -250: return "Elite Anchor. Carrying the partnership."
        if aod > 1700: return "Iron Man. Battling the heavyweights."
        if p['s_l'] >= 3: return "Rough Night. Grind on."
        return "Pure Hustle. A consistent force."

    def simulate(self, text):
        logs = []; cur_date = "Unknown"
        for line in text.strip().split('\n'):
            line = line.strip()
            date_m = re.match(r'^(\d{1,2}-[A-Za-z]+)', line)
            if date_m: cur_date = date_m.group(1)
            elif 'W:' in line and '|' in line:
                try:
                    p = line.split('|')
                    logs.append({'date': cur_date, 'W': [x.strip() for x in p[0].split('W:')[1].split(',')], 'L': [x.strip() for x in p[1].split('L:')[1].split(',')]})
                except: continue
        
        if not logs: return pd.DataFrame()
        dates = list(dict.fromkeys([l['date'] for l in logs])); num_dates = len(dates)

        for idx, d in enumerate(dates):
            is_last = (idx == num_dates - 1)
            for p in self.players.values(): p['active'], p['s_w'], p['s_l'] = False, 0, 0
            
            for g in [x for x in logs if x['date'] == d]:
                wk = [self.get_player(n, idx, num_dates) for n in g['W']]
                lk = [self.get_player(n, idx, num_dates) for n in g['L']]
                cur_mmrs = [p['mmr'] for p in self.players.values()]
                thresh = np.percentile(cur_mmrs, 80) if cur_mmrs else 1500

                # Winners
                for i, k in enumerate(wk):
                    w = self.players[k]; opp_mmrs = [self.players[lx]['mmr'] for lx in lk]
                    if not w['active']: w['mmr_s'], w['active'] = w['mmr'], True
                    bonus = min((max(opp_mmrs) - w['mmr']) * 0.2, 80) if w['mmr'] < 1349 and (max(opp_mmrs) - w['mmr']) > 300 else 0
                    w['mmr'] += (40 + bonus); w['wins'] += 1; w['s_w'] += 1; w['peak'] = max(w['peak'], w['mmr']); w['win_streak'] += 1
                    w['t_opp'] += (sum(opp_mmrs) / 2); w['t_p_delta'] += (self.players[wk[1-i]]['mmr'] - w['mmr'])

                # Losers
                for i, k in enumerate(lk):
                    l = self.players[k]; partner = self.players[lk[1-i]]; win_mmrs = [self.players[wx]['mmr'] for wx in wk]
                    if not l['active']: l['mmr_s'], l['active'] = l['mmr'], True
                    loss = 10 if (l['wins'] + l['losses']) < 5 else 20
                    gap = l['mmr'] - partner['mmr']
                    if (l['mmr'] >= thresh and gap >= 150) or (partner['mmr'] >= thresh and (partner['mmr'] - l['mmr']) >= 150): loss = 16
                    l['mmr'] -= loss; l['losses'] += 1; l['s_l'] += 1; l['win_streak'] = 0
                    l['t_opp'] += (sum(win_mmrs) / 2); l['t_p_delta'] += (partner['mmr'] - l['mmr'])

        res = []
        for k, p in self.players.items():
            tot = p['wins'] + p['losses']
            if tot == 0: continue
            aod = round(p['t_opp'] / tot); apd = round(p['t_p_delta'] / tot)
            res.append({
                "Rank": 0, "Player": p['name'], "Tier": self.get_tier(p['mmr']), "MMR": round(p['mmr']), "Peak": round(p['peak']),
                "Session +/-": round(p['mmr'] - p['mmr_s']) if p['active'] else 0, "Avg Opponent MMR": aod, "Avg Partner Delta": apd,
                "Status": "🆕 NEW PLAYER" if p['is_new'] else ("Elite" if p['mmr'] >= thresh else "Active"),
                "Confidence": "⭐⭐⭐" if tot > 15 else "⭐⭐" if tot > 5 else "⭐",
                "Record": f"{p['wins']}-{p['losses']}", "Session": f"{p['s_w']}-{p['s_l']}", "Power Remarks": "", "w_sort": p['wins'], "key": k
            })
        
        df = pd.DataFrame(res).sort_values(by=["MMR", "w_sort"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        for i, row in df.iterrows():
            df.at[i, "Power Remarks"] = self.generate_remark(self.players[row['key']], row['Avg Partner Delta'], row['Avg Opponent MMR'], row['Rank'])
        return df.drop(columns=['w_sort', 'key'])

# ==========================================
# 🎨 UI & DASHBOARD
# ==========================================
st.set_page_config(page_title="Fadu MMR Engine v8.0", layout="wide")
if 'logs' not in st.session_state: st.session_state.logs = ""

with st.sidebar:
    st.title("🏸 Fadu League Ops")
    if BRIDGE_URL != "NOT_CONFIGURED": st.success("Registry: 🟢 Online")
    else: st.error("Registry: 🔴 Offline")
    if GROQ_API_KEY != "NOT_CONFIGURED": st.success("Groq AI: 🟢 Ready")
    else: st.error("Groq AI: 🔴 No Key")
    st.divider(); st.caption("v8.0 | Full Feature Architecture")

st.title("🏸 Fadu Badminton Power Rankings")
input_area = st.text_area("Match Logs Input:", value=st.session_state.logs, height=300)

c1, c2, c3 = st.columns([1, 1, 4])
with c1:
    if st.button("✨ AI Sanitize", type="secondary", use_container_width=True):
        with st.spinner("AI thinking..."):
            st.session_state.logs = ai_sanitize_logs(input_area); st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        with st.spinner("Analyzing..."):
            engine = FaduMMREngine(ELITE_START)
            leaderboard = engine.simulate(input_area)
            st.session_state.lb = leaderboard
            if BRIDGE_URL != "NOT_CONFIGURED":
                requests.post(BRIDGE_URL, json={"target": "Registry", "headers": leaderboard.columns.tolist(), "values": leaderboard.values.tolist()})
                st.toast("Registry Synced!")

if 'lb' in st.session_state:
    st.divider()
    search = st.text_input("🔍 Search Player:", placeholder="Type a name to filter the table...")
    display_df = st.session_state.lb
    if search: display_df = display_df[display_df['Player'].str.contains(search, case=False)]
    st.dataframe(display_df, use_container_width=True, hide_index=True)