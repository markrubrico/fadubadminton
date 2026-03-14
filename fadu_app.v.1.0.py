import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json
from datetime import datetime
import time

# ==========================================
# ⚙️ LEAGUE CONFIGURATION & HEADSTARTS
# ==========================================
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

try:
    BRIDGE_URL = st.secrets["BRIDGE_URL"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    BRIDGE_URL = "NOT_CONFIGURED"
    GEMINI_API_KEY = "NOT_CONFIGURED"

# ==========================================
# 🎨 CUSTOM CSS UI ENHANCEMENTS
# ==========================================
st.markdown("""
    <style>
    .main { background-color: #f8f9fb; }
    .stDataFrame { border: 1px solid #e6e9ef; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
    div[data-testid="stMetric"] { background-color: #ffffff; border: 1px solid #e6e9ef; padding: 15px; border-radius: 12px; }
    h1, h2, h3 { color: #1e293b; font-weight: 700; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# ✨ ADVANCED AI SANITIZER (STABLE REST API)
# ==========================================
def ai_sanitize_logs(raw_input):
    if GEMINI_API_KEY == "NOT_CONFIGURED":
        return "ERROR: Missing API Key in Streamlit Secrets."
    
    # URL Path specifically corrected to v1beta/models/gemini-1.5-flash
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    You are a Master Data Parser for the Fadu Badminton League. 
    Transform messy logs into: 'Game X: W: P1, P2 | L: P3, P4'
    Logic: Identify winners/losers from context. Map nicknames to the official names in: {ELITE_START}. 
    Keep Date Headers (e.g. 20-Feb). Return ONLY cleaned logs.
    INPUT: {raw_input}
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=25)
        # Fallback to standard v1 if v1beta fails
        if response.status_code == 404:
            url_v1 = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            response = requests.post(url_v1, headers=headers, data=json.dumps(payload), timeout=25)
            
        res_json = response.json()
        if "candidates" in res_json:
            return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        return f"AI Error: {res_json.get('error', {}).get('message', 'Key Issue')}"
            
    except Exception as e:
        return f"Request Error: {str(e)}"

# ==========================================
# 🧠 DYNAMIC MMR ENGINE v4.5 (MODULAR)
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
                'display_name': n_clean, 'mmr': start_mmr, 'peak': start_mmr, 'wins': 0, 'losses': 0,
                'total_opp_mmr': 0, 'total_partner_mmr_delta': 0, 'mmr_start_of_session': start_mmr, 
                'session_w': 0, 'session_l': 0, 'last_session_idx': -1, 'is_new_to_league': True, 
                'active_this_session': False, 'win_streak': 0
            }
        return n_lower

    def get_tier(self, mmr):
        for tier, threshold in TIERS.items():
            if mmr >= threshold: return tier
        return "Master"

    def generate_power_remark(self, p, apd, aod, elite_thresh, rank):
        if p.get('is_new_to_league', False) and p['active_this_session']:
            return f"Welcome! Rookie debut with {p['session_w']}-{p['session_l']} record."
        if rank == 1: return "The Final Boss. Absolute League Dominance."
        if p['win_streak'] >= 3: return f"On Fire! {p['win_streak']} Game Win Streak."
        if apd < -250: return "The Anchor. Carrying the partnership weight."
        if aod > 1650: return "Iron Man. Battling the league heavyweights."
        if p['session_l'] >= 3: return "Rough Night. The grind continues."
        return "Pure Hustle. A consistent force."

    def simulate(self, raw_log_text):
        structured_logs = self.parse_raw_logs(raw_log_text)
        if not structured_logs: return pd.DataFrame()
        all_dates = list(dict.fromkeys([l['date'] for l in structured_logs]))
        last_session_idx = len(all_dates) - 1

        for session_idx, date in enumerate(all_dates):
            is_last = (session_idx == last_session_idx)
            session_games = [g for g in structured_logs if g['date'] == date]
            for p in self.players.values(): p['active_this_session'], p['session_w'], p['session_l'] = False, 0, 0

            for game in session_games:
                win_keys = [self.get_player(n) for n in game['W']]
                lose_keys = [self.get_player(n) for n in game['L']]
                active_mmrs = [p['mmr'] for p in self.players.values()]
                elite_thresh = np.percentile(active_mmrs, 80) if active_mmrs else 1500

                # Winners
                for i, wk in enumerate(win_keys):
                    w = self.players[wk]
                    if not w['active_this_session']: w['mmr_start_of_session'], w['active_this_session'] = w['mmr'], True
                    eff = 0 if (session_idx - w['last_session_idx'] >= 4) else (w['wins'] + w['losses'])
                    lam = 0.40 if eff <= 5 else 0.25 if eff <= 15 else 0.15
                    h_opp = max([self.players[lk]['mmr'] for lk in lose_keys]) if lose_keys else 1000
                    bonus = min((h_opp - w['mmr']) * lam, 80) if w['mmr'] < 1349 and (h_opp - w['mmr']) >= 300 else 0
                    w['mmr'] += (40 + bonus); w['wins'] += 1; w['session_w'] += 1; w['win_streak'] += 1; w['peak'] = max(w['peak'], w['mmr'])
                    w['total_opp_mmr'] += (sum([self.players[lk]['mmr'] for lk in lose_keys]) / 2)
                    w['total_partner_mmr_delta'] += (self.players[win_keys[1-i]]['mmr'] - w['mmr'])

                # Losers (Guardian Shield)
                for i, lk in enumerate(lose_keys):
                    l = self.players[lk]; partner = self.players[lose_keys[1-i]]
                    if not l['active_this_session']: l['mmr_start_of_session'], l['active_this_session'] = l['mmr'], True
                    loss = 10 if (l['wins'] + l['losses']) < 5 else 20
                    gap = l['mmr'] - partner['mmr']
                    if (l['mmr'] >= elite_thresh and gap >= 150) or (partner['mmr'] >= elite_thresh and (partner['mmr'] - l['mmr']) >= 150): loss = 16
                    l['mmr'] -= loss; l['losses'] += 1; l['session_l'] += 1; l['win_streak'] = 0
                    l['total_opp_mmr'] += (sum([self.players[wk]['mmr'] for wk in win_keys]) / 2)
                    l['total_partner_mmr_delta'] += (partner['mmr'] - l['mmr'])

            if not is_last:
                for p in self.players.values():
                    if p['active_this_session']: p['is_new_to_league'], p['last_session_idx'] = False, session_idx
        return self.generate_leaderboard(elite_thresh if 'elite_thresh' in locals() else 1500)

    def parse_raw_logs(self, text):
        logs = []
        date = "Unknown"
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('!!'): continue
            date_match = re.match(r'^(\d{1,2}-[A-Za-z]+)', line)
            if date_match: date = date_match.group(1)
            elif 'W:' in line:
                try:
                    parts = line.split('|')
                    w = [n.strip() for n in parts[0].split('W:')[1].split(',')]
                    l = [n.strip() for n in parts[1].split('L:')[1].split(',')]
                    logs.append({'date': date, 'W': w, 'L': l})
                except: continue
        return logs

    def generate_leaderboard(self, elite_thresh):
        data = []
        for key, p in self.players.items():
            total = p['wins'] + p['losses']
            if total == 0: continue
            aod = round(p['total_opp_mmr'] / total); apd = round(p['total_partner_mmr_delta'] / total)
            data.append({
                "Rank": 0, "Player": p['display_name'], "Tier": self.get_tier(p['mmr']), "MMR": round(p['mmr']),
                "Peak": round(p['peak']), "Session Change": round(p['mmr'] - p['mmr_start_of_session']) if p['active_this_session'] else 0,
                "Avg Opponent MMR": aod, "Avg Partner Delta": apd, "Status": "Elite" if p['mmr'] >= elite_thresh else "Stable",
                "Confidence": "⭐⭐⭐" if total > 15 else "⭐⭐" if total > 5 else "⭐",
                "Record": f"{p['wins']}-{p['losses']}", "Session": f"{p['session_w']}-{p['session_l']}", "w": p['wins']
            })
        df = pd.DataFrame(data).sort_values(by=["MMR", "w"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        df["Power Remarks"] = df.apply(lambda row: self.generate_power_remark(self.players[row['Player'].lower()], row['Avg Partner Delta'], row['Avg Opponent MMR'], elite_thresh, row['Rank']), axis=1)
        return df.drop(columns=['w'])

# ==========================================
# 📊 STREAMLIT DASHBOARD UI
# ==========================================
st.set_page_config(page_title="Fadu MMR Engine v1.75", layout="wide")
if 'cleaned_logs_state' not in st.session_state: st.session_state.cleaned_logs_state = ""

with st.sidebar:
    st.title("Fadu League Ops")
    st.success("Sheets: 🟢") if BRIDGE_URL != "NOT_CONFIGURED" else st.error("Sheets: 🔴")
    if GEMINI_API_KEY != "NOT_CONFIGURED":
        try:
            r = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash?key={GEMINI_API_KEY}", timeout=5)
            st.success("AI: 🟢 READY") if r.status_code == 200 else st.error("AI: 🟡 Error")
        except: st.error("AI: 🔴 Offline")
    st.info("**Brackets**\nMythic Glory: 2750+\nMythic: 2300\nLegend: 1900\nEpic: 1650\nGM: 1350")

st.title("🏸 Fadu Badminton Power Rankings")
input_logs = st.text_area("Paste Raw Match Logs:", value=st.session_state.cleaned_logs_state, height=350)

c1, c2, _ = st.columns([1.5, 1.5, 4])
with c1:
    if st.button("✨ AI Sanitize Logs", type="secondary", use_container_width=True):
        if not input_logs: st.warning("Paste logs first.")
        else:
            with st.spinner("AI Parsing..."):
                st.session_state.cleaned_logs_state = ai_sanitize_logs(input_logs)
                st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not input_logs: st.warning("No logs.")
        else:
            with st.spinner("Calculating..."):
                engine = FaduMMREngine(ELITE_START)
                res = engine.simulate(input_logs)
                st.dataframe(res, use_container_width=True, hide_index=True)
                if BRIDGE_URL != "NOT_CONFIGURED":
                    requests.post(BRIDGE_URL, json={"target": "Registry", "headers": res.columns.tolist(), "values": res.values.tolist()})
                    st.success("Synced!")
st.caption(f"v1.75 | {datetime.now().strftime('%Y-%m-%d')}")