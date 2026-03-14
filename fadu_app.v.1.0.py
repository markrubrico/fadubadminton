import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json
import google.generativeai as genai

# ==========================================
# ⚙️ CONFIGURATION & ROSTER
# ==========================================
SEEDS = [
    "Kenmore", "Lance", "Sam", "Jerome", "Pacs", "VJ", "Luke", 
    "Kent", "Ivan", "Efren", "Jayson", "Allen", "Bombi", "AJ"
]

# Fetch Secrets
try:
    BRIDGE_URL = st.secrets["BRIDGE_URL"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    BRIDGE_URL = "NOT_CONFIGURED"
    GEMINI_API_KEY = "NOT_CONFIGURED"

# ==========================================
# ✨ AI SANITIZER MODULE
# ==========================================
def ai_sanitize_logs(raw_input, roster):
    if GEMINI_API_KEY == "NOT_CONFIGURED":
        return "ERROR: Please configure GEMINI_API_KEY in Streamlit Secrets."
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        You are a data cleaning assistant for Fadu Badminton League.
        
        OFFICIAL ROSTER: {roster}
        
        TASK:
        1. Clean the provided match logs.
        2. Correct misspellings to match the Official Roster (e.g., 'Knt' -> 'Kent').
        3. Format every game exactly as: 'Game X: W: Player1, Player2 | L: Player3, Player4'
        4. Keep the Date headers (e.g., '20-Feb').
        5. If a game has the wrong number of players or is confusing, add a comment line starting with '!! CHECK:' below that game.
        
        INPUT LOGS:
        {raw_input}
        
        Strictly return ONLY the cleaned text.
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Error: {str(e)}"

# ==========================================
# 🧠 FULL MMR ENGINE v4.32
# ==========================================
class FaduMMREngineV43:
    def __init__(self, seeded_players):
        self.seeded_names = [self.clean_name(n) for n in seeded_players]
        self.players = {}
        self.all_sessions = []

    def clean_name(self, name):
        return str(name).strip().replace("  ", " ").replace(" ", "")

    def get_player(self, name):
        name = self.clean_name(name)
        if name not in self.players:
            start_mmr = 1500 if name in self.seeded_names else 1000
            self.players[name] = {
                'mmr': start_mmr, 'peak': start_mmr, 'wins': 0, 'losses': 0,
                'total_opp_mmr': 0, 'total_partner_mmr_delta': 0,
                'mmr_start_of_session': start_mmr, 'session_w': 0, 'session_l': 0,
                'last_session_idx': -1, 'is_new_to_league': True, 'active_this_session': False
            }
        return name

    def get_tier(self, mmr):
        if mmr < 1349: return "Master"
        elif mmr < 1649: return "Grandmaster"
        elif mmr < 1899: return "Epic"
        elif mmr < 2299: return "Legend"
        elif mmr < 2749: return "Mythic"
        return "Mythical Glory"

    def generate_power_remark(self, p, apd, aod, elite_thresh, rank):
        if p.get('is_new_to_league', False) and p['active_this_session']:
            return f"Welcome! Rookie debut with {p['session_w']}-{p['session_l']} record."
        if rank == 1: return "The Final Boss. Putting the league on notice."
        if p['session_w'] >= 3: return "Heat Check! Unstoppable force this session."
        if apd < -250: return "Elite Playmaker. Handling the load with poise."
        if aod > 1450: return "Iron Man. Battletested against the heavyweights."
        if p['session_l'] >= 3: return "Rough Night. The grind continues next session."
        return "Pure Hustle. A consistent force on the court."

    def simulate(self, raw_log_text):
        structured_logs = self.parse_raw_logs(raw_log_text)
        if not structured_logs: return pd.DataFrame()
        
        self.all_sessions = list(dict.fromkeys([l['date'] for l in structured_logs]))
        last_session_idx = len(self.all_sessions) - 1

        for session_idx, date in enumerate(self.all_sessions):
            is_last_session = (session_idx == last_session_idx)
            session_games = [g for g in structured_logs if g['date'] == date]
            for p in self.players.values():
                p['active_this_session'] = False
                p['session_w'] = 0
                p['session_l'] = 0

            for game in session_games:
                win_names = [self.get_player(n) for n in game['W']]
                lose_names = [self.get_player(n) for n in game['L']]
                active_mmrs = [p['mmr'] for p in self.players.values()]
                elite_thresh = np.percentile(active_mmrs, 80) if active_mmrs else 1500

                for i, w_name in enumerate(win_names):
                    w = self.players[w_name]
                    if not w['active_this_session']:
                        w['mmr_start_of_session'], w['active_this_session'] = w['mmr'], True
                    eff_games = 0 if (session_idx - w['last_session_idx'] >= 4) else (w['wins'] + w['losses'])
                    lam = 0.40 if eff_games <= 5 else 0.25 if eff_games <= 15 else 0.15
                    highest_opp = max(self.players[ln]['mmr'] for ln in lose_names)
                    bonus = min((highest_opp - w['mmr']) * lam, 80) if w['mmr'] < 1349 and (highest_opp - w['mmr']) >= 300 else 0
                    w['mmr'] += (40 + bonus)
                    w['wins'] += 1
                    w['session_w'] += 1
                    w['total_opp_mmr'] += (sum(self.players[ln]['mmr'] for ln in lose_names) / 2)
                    w['total_partner_mmr_delta'] += (self.players[win_names[1-i]]['mmr'] - w['mmr'])
                    w['peak'] = max(w['peak'], w['mmr'])

                for i, l_name in enumerate(lose_names):
                    l = self.players[l_name]
                    if not l['active_this_session']:
                        l['mmr_start_of_session'], l['active_this_session'] = l['mmr'], True
                    loss_amt, partner = 20, self.players[lose_names[1-i]]
                    if (l['wins'] + l['losses']) < 5: loss_amt = 10
                    gap = l['mmr'] - partner['mmr']
                    if l['mmr'] >= elite_thresh and gap >= 150:
                        loss_amt = 16 if gap < 300 else 12 if gap < 500 else 8
                    elif partner['mmr'] >= elite_thresh and (partner['mmr'] - l['mmr']) >= 150:
                        loss_amt = 16
                    l['mmr'] -= loss_amt
                    l['losses'] += 1
                    l['session_l'] += 1
                    l['total_opp_mmr'] += (sum(self.players[wn]['mmr'] for wn in win_names) / 2)
                    l['total_partner_mmr_delta'] += (partner['mmr'] - l['mmr'])

            if not is_last_session:
                for p in self.players.values():
                    if p['active_this_session']:
                        p['is_new_to_league'] = False
                        p['last_session_idx'] = session_idx

        return self.generate_leaderboard(elite_thresh)

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
                    w_str = parts[0].split('W:')[1].strip()
                    l_str = parts[1].split('L:')[1].strip()
                    logs.append({'date': date, 'W': [x.strip() for x in w_str.split(',')], 'L': [x.strip() for x in l_str.split(',')]})
                except: continue
        return logs

    def generate_leaderboard(self, elite_thresh):
        data = []
        for name, p in self.players.items():
            total = p['wins'] + p['losses']
            aod = round(p['total_opp_mmr'] / total) if total > 0 else 0
            apd = round(p['total_partner_mmr_delta'] / total) if total > 0 else 0
            data.append({
                "Rank": 0, "Player": name, "Tier": self.get_tier(p['mmr']), "MMR": round(p['mmr']),
                "Peak": round(p['peak']), "Session Change": round(p['mmr'] - p['mmr_start_of_session']) if p['active_this_session'] else 0,
                "Avg Opponent MMR": aod, "Avg Partner Delta": apd, "Status": "Elite" if p['mmr'] >= elite_thresh else "Stable",
                "Confidence": "⭐⭐⭐" if total > 15 else "⭐⭐" if total > 5 else "⭐",
                "Record": f"{p['wins']}-{p['losses']}", "Session": f"{p['session_w']}-{p['session_l']}", "total_wins": p['wins']
            })
        df = pd.DataFrame(data).sort_values(by=["MMR", "total_wins"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        df["Power Remarks"] = df.apply(lambda row: self.generate_power_remark(self.players[row['Player']], row['Avg Partner Delta'], row['Avg Opponent MMR'], elite_thresh, row['Rank']), axis=1)
        return df.drop(columns=['total_wins'])

# ==========================================
# 🎨 STREAMLIT INTERFACE
# ==========================================
st.set_page_config(page_title="Fadu MMR Engine v1.1", layout="wide", page_icon="🏸")

with st.sidebar:
    st.header("⚙️ Connections")
    if BRIDGE_URL == "NOT_CONFIGURED": st.error("Sheets: 🔴")
    else: st.success("Sheets: 🟢")
    
    if GEMINI_API_KEY == "NOT_CONFIGURED": st.error("AI Sanitizer: 🔴")
    else: st.success("AI Sanitizer: 🟢")
    
    st.divider()
    st.markdown("### 📋 Instructions")
    st.caption("1. Paste messy logs.")
    st.caption("2. Click 'AI Sanitize' to fix names.")
    st.caption("3. Click 'Calculate & Sync'.")

st.title("🏸 Fadu Badminton Power Rankings")

# This creates a persistent state for the logs so AI can update them
if 'clean_logs' not in st.session_state:
    st.session_state.clean_logs = ""

input_logs = st.text_area("Match Logs Input:", value=st.session_state.clean_logs, height=350)

c1, c2, c3 = st.columns([1, 1, 4])

with c1:
    if st.button("✨ AI Sanitize", type="secondary", use_container_width=True):
        if not input_logs:
            st.warning("Paste logs first!")
        else:
            with st.spinner("AI is cleaning logs..."):
                st.session_state.clean_logs = ai_sanitize_logs(input_logs, SEEDS)
                st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not input_logs:
            st.warning("No data to process.")
        else:
            with st.spinner("Processing MMR..."):
                try:
                    engine = FaduMMREngineV43(SEEDS)
                    leaderboard = engine.simulate(input_logs)
                    st.subheader("🏆 Live Results")
                    st.dataframe(leaderboard, use_container_width=True, hide_index=True)
                    
                    if BRIDGE_URL != "NOT_CONFIGURED":
                        payload = {"target": "Registry", "headers": leaderboard.columns.tolist(), "values": leaderboard.values.tolist()}
                        requests.post(BRIDGE_URL, data=json.dumps(payload))
                        st.balloons()
                        st.success("Synced to Google Sheets!")
                except Exception as e:
                    st.error(f"Error: {e}")

st.divider()
st.caption("v1.1 | AI Powered Logic")