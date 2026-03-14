import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json

# ==========================================
# ⚙️ CONFIGURATION & SEEDING (COMPLIANT)
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
    BRIDGE_URL = "NOT_CONFIGURED"
    GROQ_API_KEY = "NOT_CONFIGURED"

# ==========================================
# 🔍 AI AUDITOR (DUPE, TYPO & DEBUT HUNTER)
# ==========================================
def ai_audit_session(raw_input, established_players):
    if GROQ_API_KEY == "NOT_CONFIGURED": return "ERROR: Missing GROQ_API_KEY."
    
    blocks = raw_input.strip().split('\n\n')
    active_session = blocks[-1] if blocks else raw_input
    historical_logs = "\n".join(blocks[:-1]) if len(blocks) > 1 else "No history provided."

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
    You are the Senior Auditor for Fadu Badminton. 
    Analyze the ACTIVE SESSION vs HISTORICAL LOGS.
    ROSTER: {established_players}
    
    TASKS:
    1. DUPLICATE DATE: Flag if active date exists in history.
    2. TYPOS: Flag phonetic near-misses (e.g., Mich/Mitch, Bradd/Brad).
    3. DEBUTS: Flag names not in established roster.
    
    OUTPUT: Markdown Table with Name, Issue Type, Suggestion, and Game X.
    """
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": f"{prompt}\n\nACTIVE:\n{active_session}"}],
        "temperature": 0.0
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e: return f"Audit Error: {str(e)}"

# ==========================================
# 🧠 MMR ENGINE (FULL 13-COLUMN ARCHITECTURE)
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
        if p['s_l'] >= 3: return "Rough Night. The grind continues."
        return "Pure Hustle. A consistent force."

    def simulate(self, text):
        # Crash-Proof Guard for Empty Input
        if not text.strip(): return pd.DataFrame(), "None", sorted(list(set(self.elite_list)))
        
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
        
        if not logs: return pd.DataFrame(), cur_date, sorted(list(set(self.elite_list)))
        
        dates = list(dict.fromkeys([l['date'] for l in logs])); num_dates = len(dates)
        last_date = dates[-1]; established_names = set(self.elite_list)

        for idx, d in enumerate(dates):
            is_last = (idx == num_dates - 1)
            for p in self.players.values(): p['active'], p['s_w'], p['s_l'] = False, 0, 0
            
            for g in [x for x in logs if x['date'] == d]:
                wk = [self.get_player(n, idx, num_dates) for n in g['W']]
                lk = [self.get_player(n, idx, num_dates) for n in g['L']]
                if not is_last: established_names.update(wk); established_names.update(lk)
                
                cur_mmrs = [p['mmr'] for p in self.players.values()]; thresh = np.percentile(cur_mmrs, 80) if cur_mmrs else 1500

                # Winners (Giant Slayer Logic Included)
                for i, k in enumerate(wk):
                    w = self.players[k]; opp_mmrs = [self.players[lx]['mmr'] for lx in lk]
                    if not w['active']: w['mmr_s'], w['active'] = w['mmr'], True
                    bonus = min((max(opp_mmrs) - w['mmr']) * 0.2, 80) if w['mmr'] < 1349 and (max(opp_mmrs) - w['mmr']) > 300 else 0
                    w['mmr'] += (40 + bonus); w['wins'] += 1; w['s_w'] += 1; w['peak'] = max(w['peak'], w['mmr']); w['win_streak'] += 1
                    w['t_opp'] += (sum(opp_mmrs) / 2); w['t_p_delta'] += (self.players[wk[1-i]]['mmr'] - w['mmr'])

                # Losers (Guardian & Rookie Shield Included)
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
        return df.drop(columns=['w_sort', 'key']), last_date, sorted(list(established_names))

# ==========================================
# 🎨 UI & DASHBOARD (WIDESCREEN)
# ==========================================
st.set_page_config(page_title="Fadu MMR Engine v10.2.2", layout="wide")

with st.sidebar:
    st.title("🏸 Fadu Ops")
    # Clean Sidebar Logic (Prevents DeltaGenerator Text Leaks)
    if BRIDGE_URL != "NOT_CONFIGURED":
        st.success("Sheets Registry: 🟢 Online")
    else:
        st.error("Sheets Registry: 🔴 Offline")
    if GROQ_API_KEY != "NOT_CONFIGURED":
        st.success("AI Auditor: 🟢 Online")
    else:
        st.error("AI Auditor: 🔴 No Key")
    st.divider(); st.caption("v10.2.2 | Ironclad Build")

st.title("🏸 Fadu Badminton Power Rankings")
input_area = st.text_area("Match Logs Input:", height=300, placeholder="Paste your logs here...")

c1, c2, _ = st.columns([1.5, 1.5, 4])
with c1:
    if st.button("🔍 Run Session Audit", use_container_width=True):
        if not input_area.strip(): st.warning("Please paste logs first.")
        else:
            with st.spinner("Analyzing for duplicates and typos..."):
                engine = FaduMMREngine(ELITE_START)
                _, _, established = engine.simulate(input_area)
                st.session_state.audit_report = ai_audit_session(input_area, established)

if 'audit_report' in st.session_state:
    st.info(f"### 📋 Active Session Audit\n{st.session_state.audit_report}")
    if st.button("Close Audit"): del st.session_state.audit_report; st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not input_area.strip(): st.warning("Please paste logs first.")
        else:
            with st.spinner("Processing..."):
                engine = FaduMMREngine(ELITE_START)
                lb, last_date, _ = engine.simulate(input_area)
                st.session_state.lb, st.session_state.last_date = lb, last_date
                if BRIDGE_URL != "NOT_CONFIGURED":
                    resp = requests.post(BRIDGE_URL, json={"target": "Registry", "headers": lb.columns.tolist(), "values": lb.values.tolist()})
                    if resp.status_code == 200: st.toast(f"✅ Sync Successful: {len(lb)} rows updated.")
                    else: st.error(f"❌ Sync Failed: {resp.text}")

if 'lb' in st.session_state:
    st.divider()
    st.subheader(f"📅 Session: {st.session_state.last_date}")
    search = st.text_input("🔍 Search Player:", placeholder="Filter by name...")
    df_disp = st.session_state.lb
    if search: df_disp = df_disp[df_disp['Player'].str.contains(search, case=False)]
    st.dataframe(df_disp, use_container_width=True, hide_index=True)