import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json
from datetime import datetime

# ==========================================
# ⚙️ LEAGUE CONFIGURATION
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
# 🔍 AI AUDITOR (FOCUSED ON ACTIVE DATE)
# ==========================================
def ai_audit_logs(raw_input):
    if GROQ_API_KEY == "NOT_CONFIGURED": return "ERROR: Missing GROQ_API_KEY."
    
    # Extract only the last date block for the AI to focus on
    blocks = raw_input.strip().split('\n\n')
    active_session = blocks[-1] if blocks else raw_input

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
    You are the Auditor for the Fadu Badminton League. 
    Review ONLY this most recent session and list specific concerns.
    
    CHECK FOR:
    1. Games with missing players (must have 2 winners, 2 losers).
    2. Unknown names not in the roster: {ELITE_START}.
    
    FORMAT: 
    - [Game X]: [Reason]
    
    If this specific session looks perfect, say 'Active Session Verified: No issues found.'
    DO NOT review historical games.
    """
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": f"{prompt}\n\nACTIVE SESSION DATA:\n{active_session}"}],
        "temperature": 0.0
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e: return f"Audit Error: {str(e)}"

# ==========================================
# 🧠 DYNAMIC MMR ENGINE v9.1
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
        if p['is_new']: return "🆕 New Player debut. Welcome!"
        if rank == 1: return "The Final Boss. Absolute League Dominance."
        if p['win_streak'] >= 3: return f"Heat Check! {p['win_streak']} Win Streak."
        if apd < -250: return "Elite Anchor. Carrying the partnership."
        if aod > 1700: return "Iron Man. Battling the heavyweights."
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
                    w_list = [x.strip() for x in p[0].split('W:')[1].split(',')]
                    l_list = [x.strip() for x in p[1].split('L:')[1].split(',')]
                    if len(w_list) >= 2 and len(l_list) >= 2:
                        logs.append({'date': cur_date, 'W': w_list, 'L': l_list})
                except: continue
        
        if not logs: return pd.DataFrame()
        dates = list(dict.fromkeys([l['date'] for l in logs])); num_dates = len(dates)

        for idx, d in enumerate(dates):
            is_last = (idx == num_dates - 1)
            for p in self.players.values(): p['active'], p['s_w'], p['s_l'] = False, 0, 0
            
            for g in [x for x in logs if x['date'] == d]:
                wk = [self.get_player(n, idx, num_dates) for n in g['W']]
                lk = [self.get_player(n, idx, num_dates) for n in g['L']]
                cur_mmrs = [p['mmr'] for p in self.players.values()]; thresh = np.percentile(cur_mmrs, 80) if cur_mmrs else 1500

                for i, k in enumerate(wk):
                    w = self.players[k]; opp_mmrs = [self.players[lx]['mmr'] for lx in lk]
                    if not w['active']: w['mmr_s'], w['active'] = w['mmr'], True
                    bonus = min((max(opp_mmrs) - w['mmr']) * 0.2, 80) if w['mmr'] < 1349 and (max(opp_mmrs) - w['mmr']) > 300 else 0
                    w['mmr'] += (40 + bonus); w['wins'] += 1; w['s_w'] += 1; w['peak'] = max(w['peak'], w['mmr']); w['win_streak'] += 1
                    w['t_opp'] += (sum(opp_mmrs) / 2); w['t_p_delta'] += (self.players[wk[1-i]]['mmr'] - w['mmr'])

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
st.set_page_config(page_title="Fadu MMR Engine v9.1", layout="wide")

with st.sidebar:
    st.title("🏸 Fadu Ops")
    st.success("Sheets: 🟢") if BRIDGE_URL != "NOT_CONFIGURED" else st.error("Sheets: 🔴")
    st.success("AI Auditor: 🟢") if GROQ_API_KEY != "NOT_CONFIGURED" else st.error("AI Auditor: 🔴")
    st.divider(); st.caption("v9.1 | Isolated Audit")

st.title("🏸 Fadu Badminton Power Rankings")
input_area = st.text_area("Match Logs Input:", height=300)

c1, c2, _ = st.columns([1, 1, 4])
with c1:
    if st.button("🔍 AI Audit Logs", type="secondary", use_container_width=True):
        if not input_area: st.warning("Paste logs first.")
        else:
            with st.spinner("Auditing active session..."):
                report = ai_audit_logs(input_area)
                st.session_state.audit_report = report

# Render Audit Report in a Wide Container
if 'audit_report' in st.session_state:
    st.info(f"### 📋 Active Session Audit\n{st.session_state.audit_report}")
    if st.button("Clear Audit"): del st.session_state.audit_report; st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not input_area: st.warning("No logs to process.")
        else:
            with st.spinner("Analyzing performance..."):
                engine = FaduMMREngine(ELITE_START)
                st.session_state.lb = engine.simulate(input_area)
                if BRIDGE_URL != "NOT_CONFIGURED":
                    requests.post(BRIDGE_URL, json={"target": "Registry", "headers": st.session_state.lb.columns.tolist(), "values": st.session_state.lb.values.tolist()})
                    st.toast("Registry Synced!")

if 'lb' in st.session_state:
    st.divider()
    search = st.text_input("🔍 Search Player:", placeholder="Filter by name...")
    df = st.session_state.lb
    if search: df = df[df['Player'].str.contains(search, case=False)]
    st.dataframe(df, use_container_width=True, hide_index=True)