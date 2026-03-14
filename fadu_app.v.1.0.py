import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json
from datetime import datetime

# ==========================================
# ⚙️ LEAGUE CONFIGURATION & HEADSTARTS
# ==========================================
ELITE_START = [
    "Kenmore", "Lance", "Sam", "Jerome", "Pacs", "VJ", "Luke", 
    "Kent", "Ivan", "Efren", "Jayson", "Allen", "Bombi", "AJ"
]

# TIER DEFINITIONS (Fadu Operations Manual)
TIERS = {
    "Mythical Glory": 2750,
    "Mythic": 2300,
    "Legend": 1900,
    "Epic": 1650,
    "Grandmaster": 1350,
    "Master": 0
}

# Fetch Secrets
try:
    BRIDGE_URL = st.secrets["BRIDGE_URL"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    BRIDGE_URL = "NOT_CONFIGURED"
    GEMINI_API_KEY = "NOT_CONFIGURED"

# ==========================================
# 🎨 CUSTOM STYLES (THE "600-LINE" LOOK)
# ==========================================
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stDataFrame { border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .stMetric { background-color: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# ✨ ADVANCED AI SANITIZER (REST API)
# ==========================================
def ai_sanitize_logs(raw_input):
    if GEMINI_API_KEY == "NOT_CONFIGURED":
        return "ERROR: Missing API Key."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    You are a Master Data Parser for the Fadu Badminton League. 
    Your goal is to transform messy, human-written logs into a rigid programmatic format for an MMR Engine.

    OFFICIAL ROSTER FOR TYPO-FIXING: {ELITE_START}

    RULES:
    1. FORMAT: 'Game X: W: P1, P2 | L: P3, P4'
    2. LOGIC: Identify winners and losers from the context of sentences. 
       Example: 'Fadu and Mitch beat Kim and Lea' -> 'W: Fadu, Mitch | L: Kim, Lea'
    3. HEADERS: Keep lines starting with dates (e.g. '20-Feb') exactly as is.
    4. CONSISTENCY: Map nicknames to their most formal version (e.g. 'Pac' to 'Pacs').
    5. CLEANLINESS: Return ONLY the cleaned data. Remove emojis, chatter, and meta-comments.
    6. VALIDATION: If a game is missing a winner or has the wrong number of players, add '!! CHECK: [Reason]' below it.

    INPUT LOGS:
    {raw_input}
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=20)
        res_json = response.json()
        if "candidates" in res_json:
            return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return f"AI Error: {res_json.get('error', {}).get('message', 'Key Error')}"
    except Exception as e:
        return f"Request Error: {str(e)}"

# ==========================================
# 🧠 DYNAMIC MMR ENGINE v4.45
# ==========================================
class FaduMMREngine:
    def __init__(self, elite_list):
        self.elite_list = [n.strip().lower() for n in elite_list]
        self.players = {}
        self.raw_logs = []
        self.processed_history = []

    def get_player(self, name):
        """Initializes player with seeding logic."""
        n_clean = name.strip()
        n_lower = n_clean.lower()
        if n_lower not in self.players:
            start_mmr = 1500 if n_lower in self.elite_list else 1000
            self.players[name_lower := n_lower] = {
                'display_name': n_clean,
                'mmr': start_mmr, 
                'peak': start_mmr, 
                'wins': 0, 
                'losses': 0,
                'total_opp_mmr': 0, 
                'total_partner_mmr_delta': 0,
                'mmr_start_of_session': start_mmr, 
                'session_w': 0, 
                'session_l': 0,
                'last_session_idx': -1, 
                'is_new_to_league': True, 
                'active_this_session': False,
                'streak': 0
            }
        return n_lower

    def get_tier(self, mmr):
        for tier, threshold in TIERS.items():
            if mmr >= threshold: return tier
        return "Master"

    def generate_power_remark(self, p, apd, aod, elite_thresh, rank):
        """High-resolution remark generator with 10+ logic branches."""
        if p.get('is_new_to_league', False) and p['active_this_session']:
            return f"Welcome! Rookie debut with {p['session_w']}-{p['session_l']}."
        if rank == 1: return "The Final Boss. Absolute League Dominance."
        if rank <= 3: return "Elite Tier. Consistency at the highest level."
        if p['streak'] >= 3: return f"On Fire! {p['streak']} Game Win Streak."
        if p['session_w'] >= 3 and p['session_l'] == 0: return "Perfect Session. Unstoppable."
        if apd < -250: return "The Anchor. Hard-carrying the partnership."
        if aod > 1600: return "Iron Man. Battling the toughest opponents."
        if p['mmr'] > p['peak'] - 20: return "Peaking. Playing the best badminton yet."
        if p['session_l'] >= 3: return "Tough Night. The grind is real."
        return "Pure Hustle. A reliable force on court."

    def simulate(self, raw_log_text):
        structured_logs = self.parse_raw_logs(raw_log_text)
        if not structured_logs: return pd.DataFrame()
        
        all_dates = list(dict.fromkeys([l['date'] for l in structured_logs]))
        last_session_idx = len(all_dates) - 1

        for idx, date in enumerate(all_dates):
            is_last = (idx == last_session_idx)
            session_games = [g for g in structured_logs if g['date'] == date]
            
            # Start of Session Reset
            for p in self.players.values():
                p['active_this_session'], p['session_w'], p['session_l'] = False, 0, 0

            for game in session_games:
                win_keys = [self.get_player(n) for n in game['W']]
                lose_keys = [self.get_player(n) for n in game['L']]
                
                # Global Stats for Dynamic Shielding
                active_mmrs = [p['mmr'] for p in self.players.values()]
                elite_thresh = np.percentile(active_mmrs, 80) if active_mmrs else 1500

                # --- WINNER CALCULATIONS ---
                for i, wk in enumerate(win_keys):
                    w = self.players[wk]
                    if not w['active_this_session']:
                        w['mmr_start_of_session'], w['active_this_session'] = w['mmr'], True
                    
                    # Lambda Decay (Inactivity Check)
                    eff_games = 0 if (idx - w['last_session_idx'] >= 4) else (w['wins'] + w['losses'])
                    lam = 0.40 if eff_games <= 5 else 0.25 if eff_games <= 15 else 0.15
                    
                    # Giant Slayer Bonus
                    h_opp = max(self.players[lk]['mmr'] for lk in lose_keys)
                    bonus = min((h_opp - w['mmr']) * lam, 80) if w['mmr'] < 1349 and (h_opp - w['mmr']) >= 300 else 0
                    
                    w['mmr'] += (40 + bonus)
                    w['wins'] += 1; w['session_w'] += 1; w['streak'] += 1
                    w['peak'] = max(w['peak'], w['mmr'])
                    w['total_opp_mmr'] += (sum(self.players[lk]['mmr'] for lk in lose_keys) / 2)
                    w['total_partner_mmr_delta'] += (self.players[win_keys[1-i]]['mmr'] - w['mmr'])

                # --- LOSER CALCULATIONS ---
                for i, lk in enumerate(lose_keys):
                    l = self.players[lk]; partner = self.players[lose_keys[1-i]]
                    if not l['active_this_session']:
                        l['mmr_start_of_session'], l['active_this_session'] = l['mmr'], True
                    
                    # 1. Rookie Shield (Game 1-5)
                    loss = 10 if (l['wins'] + l['losses']) < 5 else 20
                    
                    # 2. Guardian Shields (Elite Protection)
                    gap = l['mmr'] - partner['mmr']
                    if l['mmr'] >= elite_thresh and gap >= 150:
                        # Protection for the Elite player carrying
                        loss = 16 if gap < 300 else 12 if gap < 500 else 8
                    elif partner['mmr'] >= elite_thresh and (partner['mmr'] - l['mmr']) >= 150:
                        # Protection for the lower player partnered with Elite
                        loss = 16 
                    
                    l['mmr'] -= loss; l['losses'] += 1; l['session_l'] += 1; l['streak'] = 0
                    l['total_opp_mmr'] += (sum(self.players[wk]['mmr'] for wk in win_keys) / 2)
                    l['total_partner_mmr_delta'] += (partner['mmr'] - l['mmr'])

            if not is_last:
                for p in self.players.values():
                    if p['active_this_session']:
                        p['is_new_to_league'], p['last_session_idx'] = False, idx

        return self.generate_leaderboard(elite_thresh if 'elite_thresh' in locals() else 1500)

    def parse_raw_logs(self, text):
        logs = []
        date = "Unknown"
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('!!'): continue
            date_m = re.match(r'^(\d{1,2}-[A-Za-z]+)', line)
            if date_m: 
                date = date_m.group(1)
            elif 'W:' in line:
                try:
                    parts = line.split('|')
                    w = [x.strip() for x in parts[0].split('W:')[1].split(',')]
                    l = [x.strip() for x in parts[1].split('L:')[1].split(',')]
                    logs.append({'date': date, 'W': w, 'L': l})
                except: continue
        return logs

    def generate_leaderboard(self, elite_thresh):
        data = []
        for key, p in self.players.items():
            total = p['wins'] + p['losses']
            aod = round(p['total_opp_mmr'] / total) if total > 0 else 0
            apd = round(p['total_partner_mmr_delta'] / total) if total > 0 else 0
            
            data.append({
                "Rank": 0, 
                "Player": p['display_name'], 
                "Tier": self.get_tier(p['mmr']), 
                "MMR": round(p['mmr']),
                "Peak": round(p['peak']), 
                "Session Change": round(p['mmr'] - p['mmr_start_of_session']) if p['active_this_session'] else 0,
                "Avg Opponent MMR": aod, 
                "Avg Partner Delta": apd,
                "Status": "Elite" if p['mmr'] >= elite_thresh else "Stable",
                "Confidence": "⭐⭐⭐" if total > 15 else "⭐⭐" if total > 5 else "⭐",
                "Record": f"{p['wins']}-{p['losses']}", 
                "Session": f"{p['session_w']}-{p['session_l']}",
                "total_wins": p['wins']
            })
        
        df = pd.DataFrame(data).sort_values(by=["MMR", "total_wins"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        
        # Apply Power Remarks logic
        df["Power Remarks"] = df.apply(lambda row: self.generate_power_remark(
            self.players[row['Player'].lower()], row['Avg Partner Delta'], 
            row['Avg Opponent MMR'], elite_thresh, row['Rank']), axis=1
        )
        return df.drop(columns=['total_wins'])

# ==========================================
# 🎨 STREAMLIT INTERFACE (THE "600-LINE" UI)
# ==========================================
st.set_page_config(page_title="Fadu MMR Engine v1.6", layout="wide", page_icon="🏸")

if 'clean_logs' not in st.session_state:
    st.session_state.clean_logs = ""

with st.sidebar:
    st.title("🏸 Fadu Ops")
    
    # Connection Diagnostics
    st.subheader("System Status")
    if BRIDGE_URL != "NOT_CONFIGURED": st.success("Registry Sync: 🟢 ONLINE")
    else: st.error("Registry Sync: 🔴 OFFLINE")
    
    if GEMINI_API_KEY != "NOT_CONFIGURED":
        test_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest?key={GEMINI_API_KEY}"
        try:
            r = requests.get(test_url)
            if r.status_code == 200: st.success("AI Sanitizer: 🟢 READY")
            else: st.error(f"AI Sanitizer: 🟡 ERROR {r.status_code}")
        except: st.error("AI Sanitizer: 🔴 NO CONNECTION")
    else:
        st.error("AI Sanitizer: 🔴 NO KEY")

    st.divider()
    st.subheader("Tier Thresholds")
    for tier, val in TIERS.items():
        st.caption(f"**{tier}**: {val}+")

# Main Dashboard
st.title("🏸 Fadu Badminton Power Rankings")
st.markdown("Automated ELO Engine and Registry Synchronization.")

# Input Area
logs_input = st.text_area("Input Raw Match Logs (Paste from Chat):", value=st.session_state.clean_logs, height=350)

# Action Row
c1, c2, c3 = st.columns([1.5, 1.5, 4])

with c1:
    if st.button("✨ AI Sanitize Logs", type="secondary", use_container_width=True):
        if not logs_input:
            st.warning("Input is empty.")
        else:
            with st.spinner("AI is cleaning and mapping roster..."):
                st.session_state.clean_logs = ai_sanitize_logs(logs_input)
                st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not logs_input:
            st.warning("No logs to process.")
        else:
            with st.spinner("Executing MMR Trajectories..."):
                try:
                    engine = FaduMMREngine(ELITE_START)
                    leaderboard = engine.simulate(logs_input)
                    
                    st.divider()
                    st.subheader("🏆 Official Power Rankings")
                    st.dataframe(leaderboard, use_container_width=True, hide_index=True)
                    
                    # Google Sheets Integration
                    if BRIDGE_URL != "NOT_CONFIGURED":
                        payload = {
                            "target": "Registry", 
                            "headers": leaderboard.columns.tolist(), 
                            "values": leaderboard.values.tolist()
                        }
                        sync_res = requests.post(BRIDGE_URL, json=payload, timeout=10)
                        if sync_res.status_code == 200:
                            st.balloons()
                            st.success("✅ Google Sheets Registry updated successfully!")
                        else:
                            st.error(f"Sync failed: {sync_res.text}")
                except Exception as e:
                    st.error(f"Critical Engine Error: {str(e)}")

st.divider()
st.caption(f"Fadu MMR v1.6 | Compiled {datetime.now().strftime('%Y-%m-%d %H:%M')}")import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json
from datetime import datetime

# ==========================================
# ⚙️ LEAGUE CONFIGURATION & HEADSTARTS
# ==========================================
ELITE_START = [
    "Kenmore", "Lance", "Sam", "Jerome", "Pacs", "VJ", "Luke", 
    "Kent", "Ivan", "Efren", "Jayson", "Allen", "Bombi", "AJ"
]

# TIER DEFINITIONS (Fadu Operations Manual)
TIERS = {
    "Mythical Glory": 2750,
    "Mythic": 2300,
    "Legend": 1900,
    "Epic": 1650,
    "Grandmaster": 1350,
    "Master": 0
}

# Fetch Secrets
try:
    BRIDGE_URL = st.secrets["BRIDGE_URL"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    BRIDGE_URL = "NOT_CONFIGURED"
    GEMINI_API_KEY = "NOT_CONFIGURED"

# ==========================================
# 🎨 CUSTOM STYLES (THE "600-LINE" LOOK)
# ==========================================
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stDataFrame { border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .stMetric { background-color: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# ✨ ADVANCED AI SANITIZER (REST API)
# ==========================================
def ai_sanitize_logs(raw_input):
    if GEMINI_API_KEY == "NOT_CONFIGURED":
        return "ERROR: Missing API Key."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    You are a Master Data Parser for the Fadu Badminton League. 
    Your goal is to transform messy, human-written logs into a rigid programmatic format for an MMR Engine.

    OFFICIAL ROSTER FOR TYPO-FIXING: {ELITE_START}

    RULES:
    1. FORMAT: 'Game X: W: P1, P2 | L: P3, P4'
    2. LOGIC: Identify winners and losers from the context of sentences. 
       Example: 'Fadu and Mitch beat Kim and Lea' -> 'W: Fadu, Mitch | L: Kim, Lea'
    3. HEADERS: Keep lines starting with dates (e.g. '20-Feb') exactly as is.
    4. CONSISTENCY: Map nicknames to their most formal version (e.g. 'Pac' to 'Pacs').
    5. CLEANLINESS: Return ONLY the cleaned data. Remove emojis, chatter, and meta-comments.
    6. VALIDATION: If a game is missing a winner or has the wrong number of players, add '!! CHECK: [Reason]' below it.

    INPUT LOGS:
    {raw_input}
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=20)
        res_json = response.json()
        if "candidates" in res_json:
            return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return f"AI Error: {res_json.get('error', {}).get('message', 'Key Error')}"
    except Exception as e:
        return f"Request Error: {str(e)}"

# ==========================================
# 🧠 DYNAMIC MMR ENGINE v4.45
# ==========================================
class FaduMMREngine:
    def __init__(self, elite_list):
        self.elite_list = [n.strip().lower() for n in elite_list]
        self.players = {}
        self.raw_logs = []
        self.processed_history = []

    def get_player(self, name):
        """Initializes player with seeding logic."""
        n_clean = name.strip()
        n_lower = n_clean.lower()
        if n_lower not in self.players:
            start_mmr = 1500 if n_lower in self.elite_list else 1000
            self.players[name_lower := n_lower] = {
                'display_name': n_clean,
                'mmr': start_mmr, 
                'peak': start_mmr, 
                'wins': 0, 
                'losses': 0,
                'total_opp_mmr': 0, 
                'total_partner_mmr_delta': 0,
                'mmr_start_of_session': start_mmr, 
                'session_w': 0, 
                'session_l': 0,
                'last_session_idx': -1, 
                'is_new_to_league': True, 
                'active_this_session': False,
                'streak': 0
            }
        return n_lower

    def get_tier(self, mmr):
        for tier, threshold in TIERS.items():
            if mmr >= threshold: return tier
        return "Master"

    def generate_power_remark(self, p, apd, aod, elite_thresh, rank):
        """High-resolution remark generator with 10+ logic branches."""
        if p.get('is_new_to_league', False) and p['active_this_session']:
            return f"Welcome! Rookie debut with {p['session_w']}-{p['session_l']}."
        if rank == 1: return "The Final Boss. Absolute League Dominance."
        if rank <= 3: return "Elite Tier. Consistency at the highest level."
        if p['streak'] >= 3: return f"On Fire! {p['streak']} Game Win Streak."
        if p['session_w'] >= 3 and p['session_l'] == 0: return "Perfect Session. Unstoppable."
        if apd < -250: return "The Anchor. Hard-carrying the partnership."
        if aod > 1600: return "Iron Man. Battling the toughest opponents."
        if p['mmr'] > p['peak'] - 20: return "Peaking. Playing the best badminton yet."
        if p['session_l'] >= 3: return "Tough Night. The grind is real."
        return "Pure Hustle. A reliable force on court."

    def simulate(self, raw_log_text):
        structured_logs = self.parse_raw_logs(raw_log_text)
        if not structured_logs: return pd.DataFrame()
        
        all_dates = list(dict.fromkeys([l['date'] for l in structured_logs]))
        last_session_idx = len(all_dates) - 1

        for idx, date in enumerate(all_dates):
            is_last = (idx == last_session_idx)
            session_games = [g for g in structured_logs if g['date'] == date]
            
            # Start of Session Reset
            for p in self.players.values():
                p['active_this_session'], p['session_w'], p['session_l'] = False, 0, 0

            for game in session_games:
                win_keys = [self.get_player(n) for n in game['W']]
                lose_keys = [self.get_player(n) for n in game['L']]
                
                # Global Stats for Dynamic Shielding
                active_mmrs = [p['mmr'] for p in self.players.values()]
                elite_thresh = np.percentile(active_mmrs, 80) if active_mmrs else 1500

                # --- WINNER CALCULATIONS ---
                for i, wk in enumerate(win_keys):
                    w = self.players[wk]
                    if not w['active_this_session']:
                        w['mmr_start_of_session'], w['active_this_session'] = w['mmr'], True
                    
                    # Lambda Decay (Inactivity Check)
                    eff_games = 0 if (idx - w['last_session_idx'] >= 4) else (w['wins'] + w['losses'])
                    lam = 0.40 if eff_games <= 5 else 0.25 if eff_games <= 15 else 0.15
                    
                    # Giant Slayer Bonus
                    h_opp = max(self.players[lk]['mmr'] for lk in lose_keys)
                    bonus = min((h_opp - w['mmr']) * lam, 80) if w['mmr'] < 1349 and (h_opp - w['mmr']) >= 300 else 0
                    
                    w['mmr'] += (40 + bonus)
                    w['wins'] += 1; w['session_w'] += 1; w['streak'] += 1
                    w['peak'] = max(w['peak'], w['mmr'])
                    w['total_opp_mmr'] += (sum(self.players[lk]['mmr'] for lk in lose_keys) / 2)
                    w['total_partner_mmr_delta'] += (self.players[win_keys[1-i]]['mmr'] - w['mmr'])

                # --- LOSER CALCULATIONS ---
                for i, lk in enumerate(lose_keys):
                    l = self.players[lk]; partner = self.players[lose_keys[1-i]]
                    if not l['active_this_session']:
                        l['mmr_start_of_session'], l['active_this_session'] = l['mmr'], True
                    
                    # 1. Rookie Shield (Game 1-5)
                    loss = 10 if (l['wins'] + l['losses']) < 5 else 20
                    
                    # 2. Guardian Shields (Elite Protection)
                    gap = l['mmr'] - partner['mmr']
                    if l['mmr'] >= elite_thresh and gap >= 150:
                        # Protection for the Elite player carrying
                        loss = 16 if gap < 300 else 12 if gap < 500 else 8
                    elif partner['mmr'] >= elite_thresh and (partner['mmr'] - l['mmr']) >= 150:
                        # Protection for the lower player partnered with Elite
                        loss = 16 
                    
                    l['mmr'] -= loss; l['losses'] += 1; l['session_l'] += 1; l['streak'] = 0
                    l['total_opp_mmr'] += (sum(self.players[wk]['mmr'] for wk in win_keys) / 2)
                    l['total_partner_mmr_delta'] += (partner['mmr'] - l['mmr'])

            if not is_last:
                for p in self.players.values():
                    if p['active_this_session']:
                        p['is_new_to_league'], p['last_session_idx'] = False, idx

        return self.generate_leaderboard(elite_thresh if 'elite_thresh' in locals() else 1500)

    def parse_raw_logs(self, text):
        logs = []
        date = "Unknown"
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('!!'): continue
            date_m = re.match(r'^(\d{1,2}-[A-Za-z]+)', line)
            if date_m: 
                date = date_m.group(1)
            elif 'W:' in line:
                try:
                    parts = line.split('|')
                    w = [x.strip() for x in parts[0].split('W:')[1].split(',')]
                    l = [x.strip() for x in parts[1].split('L:')[1].split(',')]
                    logs.append({'date': date, 'W': w, 'L': l})
                except: continue
        return logs

    def generate_leaderboard(self, elite_thresh):
        data = []
        for key, p in self.players.items():
            total = p['wins'] + p['losses']
            aod = round(p['total_opp_mmr'] / total) if total > 0 else 0
            apd = round(p['total_partner_mmr_delta'] / total) if total > 0 else 0
            
            data.append({
                "Rank": 0, 
                "Player": p['display_name'], 
                "Tier": self.get_tier(p['mmr']), 
                "MMR": round(p['mmr']),
                "Peak": round(p['peak']), 
                "Session Change": round(p['mmr'] - p['mmr_start_of_session']) if p['active_this_session'] else 0,
                "Avg Opponent MMR": aod, 
                "Avg Partner Delta": apd,
                "Status": "Elite" if p['mmr'] >= elite_thresh else "Stable",
                "Confidence": "⭐⭐⭐" if total > 15 else "⭐⭐" if total > 5 else "⭐",
                "Record": f"{p['wins']}-{p['losses']}", 
                "Session": f"{p['session_w']}-{p['session_l']}",
                "total_wins": p['wins']
            })
        
        df = pd.DataFrame(data).sort_values(by=["MMR", "total_wins"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        
        # Apply Power Remarks logic
        df["Power Remarks"] = df.apply(lambda row: self.generate_power_remark(
            self.players[row['Player'].lower()], row['Avg Partner Delta'], 
            row['Avg Opponent MMR'], elite_thresh, row['Rank']), axis=1
        )
        return df.drop(columns=['total_wins'])

# ==========================================
# 🎨 STREAMLIT INTERFACE (THE "600-LINE" UI)
# ==========================================
st.set_page_config(page_title="Fadu MMR Engine v1.6", layout="wide", page_icon="🏸")

if 'clean_logs' not in st.session_state:
    st.session_state.clean_logs = ""

with st.sidebar:
    st.title("🏸 Fadu Ops")
    
    # Connection Diagnostics
    st.subheader("System Status")
    if BRIDGE_URL != "NOT_CONFIGURED": st.success("Registry Sync: 🟢 ONLINE")
    else: st.error("Registry Sync: 🔴 OFFLINE")
    
    if GEMINI_API_KEY != "NOT_CONFIGURED":
        test_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest?key={GEMINI_API_KEY}"
        try:
            r = requests.get(test_url)
            if r.status_code == 200: st.success("AI Sanitizer: 🟢 READY")
            else: st.error(f"AI Sanitizer: 🟡 ERROR {r.status_code}")
        except: st.error("AI Sanitizer: 🔴 NO CONNECTION")
    else:
        st.error("AI Sanitizer: 🔴 NO KEY")

    st.divider()
    st.subheader("Tier Thresholds")
    for tier, val in TIERS.items():
        st.caption(f"**{tier}**: {val}+")

# Main Dashboard
st.title("🏸 Fadu Badminton Power Rankings")
st.markdown("Automated ELO Engine and Registry Synchronization.")

# Input Area
logs_input = st.text_area("Input Raw Match Logs (Paste from Chat):", value=st.session_state.clean_logs, height=350)

# Action Row
c1, c2, c3 = st.columns([1.5, 1.5, 4])

with c1:
    if st.button("✨ AI Sanitize Logs", type="secondary", use_container_width=True):
        if not logs_input:
            st.warning("Input is empty.")
        else:
            with st.spinner("AI is cleaning and mapping roster..."):
                st.session_state.clean_logs = ai_sanitize_logs(logs_input)
                st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not logs_input:
            st.warning("No logs to process.")
        else:
            with st.spinner("Executing MMR Trajectories..."):
                try:
                    engine = FaduMMREngine(ELITE_START)
                    leaderboard = engine.simulate(logs_input)
                    
                    st.divider()
                    st.subheader("🏆 Official Power Rankings")
                    st.dataframe(leaderboard, use_container_width=True, hide_index=True)
                    
                    # Google Sheets Integration
                    if BRIDGE_URL != "NOT_CONFIGURED":
                        payload = {
                            "target": "Registry", 
                            "headers": leaderboard.columns.tolist(), 
                            "values": leaderboard.values.tolist()
                        }
                        sync_res = requests.post(BRIDGE_URL, json=payload, timeout=10)
                        if sync_res.status_code == 200:
                            st.balloons()
                            st.success("✅ Google Sheets Registry updated successfully!")
                        else:
                            st.error(f"Sync failed: {sync_res.text}")
                except Exception as e:
                    st.error(f"Critical Engine Error: {str(e)}")

st.divider()
st.caption(f"Fadu MMR v1.6 | Compiled {datetime.now().strftime('%Y-%m-%d %H:%M')}")