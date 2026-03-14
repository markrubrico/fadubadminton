import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json
from datetime import datetime

# ==========================================
# ⚙️ LEAGUE CONFIGURATION & SEEDING
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
# 🔍 SURGICAL AI VALIDATOR (NEW PLAYERS ONLY)
# ==========================================
def ai_audit_new_players(raw_input, established_players):
    if GROQ_API_KEY == "NOT_CONFIGURED": return "ERROR: Missing GROQ_API_KEY."
    
    blocks = raw_input.strip().split('\n\n')
    active_session = blocks[-1] if blocks else raw_input

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
    You are the Data Auditor for Fadu Badminton. 
    Analyze ONLY the active session data provided below.

    KNOWN PLAYERS (Do not flag these): {established_players}

    TASK:
    Identify any names in the ACTIVE DATA that are NOT in the KNOWN PLAYERS list.
    For each suspected new player, list the specific Game Number(s) where they appear.

    OUTPUT FORMAT (Strictly Markdown Table):
    | Suspected New Player | Game Number(s) |
    | :--- | :--- |
    | Name | Game X, Game Y |

    If no new players are found, say 'All players verified against roster.'
    DO NOT list players who are already in the Known list.
    """
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": f"{prompt}\n\nACTIVE DATA:\n{active_session}"}],
        "temperature": 0.0
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e: return f"Audit Error: {str(e)}"

# ==========================================
# 🧠 DYNAMIC MMR ENGINE v10.0 (FULL 13-COL)
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
                'active': False, 'is_new': (date_idx == total_dates - 1)
            }
        return n_lower

    def get_tier(self, mmr):
        for name, threshold in TIERS:
            if mmr > threshold: return name
        return "Master"

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
        
        if not logs: return pd.DataFrame(), "None", []
        dates = list(dict.fromkeys([l['date'] for l in logs])); num_dates = len(dates)
        last_date = dates[-1]; established_names = set(self.elite_list)

        for idx, d in enumerate(dates):
            is_last = (idx == num_dates - 1)
            for p in self.players.values(): p['active'], p['s_w'], p['s_l'] = False, 0, 0
            
            for g in [x for x in logs if x['date'] == d]:
                wk = [self.get_player(n, idx, num_dates) for n in g['W']]
                lk = [self.get_player(n, idx, num_dates) for n in g['L']]
                if not is_last:
                    established_names.update(wk); established_names.update(lk)
                
                mmrs = [p['mmr'] for p in self.players.values()]; thresh = np.percentile(mmrs, 80) if mmrs else 1500
                for i, k in enumerate(wk):
                    w = self.players[k]; opp_mmrs = [self.players[lx]['mmr'] for lx in lk]
                    if not w['active']: w['mmr_s'], w['active'] = w['mmr'], True
                    # Giant Slayer Bonus (+40 Base + Bonus)
                    bonus = min((max(opp_mmrs) - w['mmr']) * 0.2, 80) if w['mmr'] < 1349 and (max(opp_mmrs) - w['mmr']) > 300 else 0
                    w['mmr'] += (40 + bonus); w['wins'] += 1; w['s_w'] += 1; w['peak'] = max(w['peak'], w['mmr'])
                    w['t_opp'] += (sum(opp_mmrs) / 2); w['t_p_delta'] += (self.players[wk[1-i]]['mmr'] - w['mmr'])
                for i, k in enumerate(lk):
                    l = self.players[k]; partner = self.players[lk[1-i]]; win_mmrs = [self.players[wx]['mmr'] for wx in wk]
                    if not l['active']: l['mmr_s'], l['active'] = l['mmr'], True
                    loss = 10 if (l['wins'] + l['losses']) < 5 else 20
                    l['mmr'] -= loss; l['losses'] += 1; l['s_l'] += 1; l['t_opp'] += (sum(win_mmrs) / 2); l['t_p_delta'] += (partner['mmr'] - l['mmr'])

        res = []
        for k, p in self.players.items():
            tot = p['wins'] + p['losses']
            if tot == 0: continue
            res.append({
                "Rank": 0, "Player": p['name'], "Tier": self.get_tier(p['mmr']), "MMR": round(p['mmr']), "Peak": round(p['peak']),
                "Session +/-": round(p['mmr'] - p['mmr_s']) if p['active'] else 0,
                "Avg Opponent MMR": round(p['t_opp']/tot), "Avg Partner Delta": round(p['t_p_delta']/tot),
                "Status": "🆕 NEW PLAYER" if p['is_new'] else ("Elite" if p['mmr'] >= thresh else "Active"),
                "Confidence": "⭐⭐⭐" if tot > 15 else "⭐⭐" if tot > 5 else "⭐",
                "Record": f"{p['wins']}-{p['losses']}", "Session": f"{p['s_w']}-{p['s_l']}", "Power Remarks": "Hustle Player.", "w_sort": p['wins']
            })
        df = pd.DataFrame(res).sort_values(by=["MMR", "w_sort"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        return df.drop(columns=['w_sort']), last_date, sorted(list(established_names))

# ==========================================
# 🎨 UI & DASHBOARD
# ==========================================
st.set_page_config(page_title="Fadu MMR Engine v10.0", layout="wide")

with st.sidebar:
    st.title("🏸 Fadu Ops")
    if BRIDGE_URL != "NOT_CONFIGURED": st.success("Registry: 🟢 Online")
    else: st.error("Registry: 🔴 Offline")
    if GROQ_API_KEY != "NOT_CONFIGURED": st.success("AI Auditor: 🟢 Ready")
    else: st.error("AI Auditor: 🔴 No Key")
    st.divider(); st.caption("v10.0 | Ironclad Auditor")

st.title("🏸 Fadu Badminton Power Rankings")
input_area = st.text_area("Match Logs Input:", height=300)

c1, c2, _ = st.columns([1.5, 1.5, 4])
with c1:
    if st.button("🔍 Audit New Players", type="secondary", use_container_width=True):
        if not input_area: st.warning("Paste logs first.")
        else:
            with st.spinner("Hunting for new debuts..."):
                engine = FaduMMREngine(ELITE_START)
                _, _, established = engine.simulate(input_area)
                st.session_state.audit_report = ai_audit_new_players(input_area, established)

if 'audit_report' in st.session_state:
    st.markdown("### 📋 Suspected Debut Report")
    st.markdown(st.session_state.audit_report)
    if st.button("Close Report"): del st.session_state.audit_report; st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not input_area: st.warning("No logs.")
        else:
            with st.spinner("Processing..."):
                engine = FaduMMREngine(ELITE_START)
                st.session_state.lb, st.session_state.last_date, _ = engine.simulate(input_area)
                if BRIDGE_URL != "NOT_CONFIGURED":
                    requests.post(BRIDGE_URL, json={"target": "Registry", "headers": st.session_state.lb.columns.tolist(), "values": st.session_state.lb.values.tolist()})
                    st.toast("Registry Synced!")

if 'lb' in st.session_state:
    st.divider()
    st.subheader(f"📅 Session Results: {st.session_state.last_date}")
    search = st.text_input("🔍 Search Player:", placeholder="Filter ranking table...")
    df = st.session_state.lb
    if search: df = df[df['Player'].str.contains(search, case=False)]
    st.dataframe(df, use_container_width=True, hide_index=True)