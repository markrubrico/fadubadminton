import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json

# ==========================================
# ⚙️ CONFIGURATION & HEADSTARTS
# ==========================================
# Veterans start at 1500 MMR. Everyone else found in the logs starts at 1000.
ELITE_START = [
    "Kenmore", "Lance", "Sam", "Jerome", "Pacs", "VJ", "Luke", 
    "Kent", "Ivan", "Efren", "Jayson", "Allen", "Bombi", "AJ"
]

# Securely fetch secrets from Streamlit Cloud
try:
    BRIDGE_URL = st.secrets["BRIDGE_URL"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    BRIDGE_URL = "NOT_CONFIGURED"
    GEMINI_API_KEY = "NOT_CONFIGURED"

# ==========================================
# ✨ STABLE AI SANITIZER (REST API)
# ==========================================
def ai_sanitize_logs(raw_input):
    if GEMINI_API_KEY == "NOT_CONFIGURED":
        return "ERROR: Missing API Key in Streamlit Secrets."
    
    # Path updated to v1beta/models/...-latest to solve the 404/NOT_FOUND issue
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    You are a Master Data Parser for the Fadu Badminton League.
    
    TASK:
    Transform messy, conversational game logs into a strict programmatic format.
    
    RULES:
    1. OUTPUT FORMAT: 'Game X: W: Winner1, Winner2 | L: Loser1, Loser2'
    2. FOOLPROOF MAPPING: Even if the input is a sentence like 'Kim, Lea vs Fadu, Mitch: WINNER - FADU, MITCH', you MUST identify that Fadu/Mitch are winners and Kim/Lea are losers.
    3. DATE HEADERS: Keep lines like '20-Feb' or '07-Mar' exactly as they are.
    4. NO CONVERSATION: Return ONLY the cleaned data without any preamble.
    
    INPUT TO PROCESS:
    {raw_input}
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15)
        res_json = response.json()
        if "candidates" in res_json:
            return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return f"AI Error: {res_json.get('error', {}).get('message', 'Check API Key Status.')}"
    except Exception as e:
        return f"Request Error: {str(e)}"

# ==========================================
# 🧠 DYNAMIC MMR ENGINE v4.32 (FULL LOGIC)
# ==========================================
class FaduMMREngine:
    def __init__(self, elite_list):
        self.elite_list = [n.strip().lower() for n in elite_list]
        self.players = {}

    def get_player(self, name):
        name_clean = name.strip()
        name_lower = name_clean.lower()
        if name_lower not in self.players:
            # Dynamic Seeding: Elite list gets 1500, others 1000
            start_mmr = 1500 if name_lower in self.elite_list else 1000
            self.players[name_lower] = {
                'display_name': name_clean,
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
                'active_this_session': False
            }
        return name_lower

    def get_tier(self, mmr):
        if mmr < 1349: return "Master"
        elif mmr < 1649: return "Grandmaster"
        elif mmr < 1899: return "Epic"
        elif mmr < 2299: return "Legend"
        elif mmr < 2749: return "Mythic"
        return "Mythical Glory"

    def generate_power_remark(self, p, apd, aod, elite_thresh, rank):
        """Official Fadu AI Commentary Logic."""
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
        
        all_dates = list(dict.fromkeys([l['date'] for l in structured_logs]))
        last_session_idx = len(all_dates) - 1

        for idx, date in enumerate(all_dates):
            is_last_session = (idx == last_session_idx)
            session_games = [g for g in structured_logs if g['date'] == date]
            
            # Reset session counters
            for p in self.players.values():
                p['active_this_session'] = False
                p['session_w'] = 0
                p['session_l'] = 0

            for game in session_games:
                win_keys = [self.get_player(n) for n in game['W']]
                lose_keys = [self.get_player(n) for n in game['L']]
                active_mmrs = [p['mmr'] for p in self.players.values()]
                elite_thresh = np.percentile(active_mmrs, 80) if active_mmrs else 1500

                # --- WINNER LOGIC (With Giant Slayer Bonus) ---
                for i, wk in enumerate(win_keys):
                    w = self.players[wk]
                    if not w['active_this_session']:
                        w['mmr_start_of_session'], w['active_this_session'] = w['mmr'], True
                    
                    # Lambda Decay Check
                    eff = 0 if (idx - w['last_session_idx'] >= 4) else (w['wins'] + w['losses'])
                    lam = 0.40 if eff <= 5 else 0.25 if eff <= 15 else 0.15
                    
                    # Giant Slayer Bonus Calc
                    h_opp = max(self.players[lk]['mmr'] for lk in lose_keys)
                    bonus = min((h_opp - w['mmr']) * lam, 80) if w['mmr'] < 1349 and (h_opp - w['mmr']) >= 300 else 0
                    
                    w['mmr'] += (40 + bonus)
                    w['wins'] += 1; w['session_w'] += 1; w['peak'] = max(w['peak'], w['mmr'])
                    w['total_opp_mmr'] += (sum(self.players[lk]['mmr'] for lk in lose_keys) / 2)
                    w['total_partner_mmr_delta'] += (self.players[win_keys[1-i]]['mmr'] - w['mmr'])

                # --- LOSER LOGIC (With Guardian Shields) ---
                for i, lk in enumerate(lose_keys):
                    l = self.players[lk]; partner = self.players[lose_keys[1-i]]
                    if not l['active_this_session']:
                        l['mmr_start_of_session'], l['active_this_session'] = l['mmr'], True
                    
                    # Rookie Shield
                    loss = 10 if (l['wins'] + l['losses']) < 5 else 20
                    
                    # Guardian Shield (Elite Carry or Partner Subsidy)
                    gap = l['mmr'] - partner['mmr']
                    if l['mmr'] >= elite_thresh and gap >= 150:
                        loss = 16 if gap < 300 else 12 if gap < 500 else 8
                    elif partner['mmr'] >= elite_thresh and (partner['mmr'] - l['mmr']) >= 150:
                        loss = 16
                    
                    l['mmr'] -= loss; l['losses'] += 1; l['session_l'] += 1
                    l['total_opp_mmr'] += (sum(self.players[wk]['mmr'] for wk in win_keys) / 2)
                    l['total_partner_mmr_delta'] += (partner['mmr'] - l['mmr'])

            if not is_last_session:
                for p in self.players.values():
                    if p['active_this_session']:
                        p['is_new_to_league'] = False
                        p['last_session_idx'] = idx

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
        
        # Apply Power Remarks
        df["Power Remarks"] = df.apply(lambda row: self.generate_power_remark(
            self.players[row['Player'].lower()], row['Avg Partner Delta'], 
            row['Avg Opponent MMR'], elite_thresh, row['Rank']), axis=1
        )
        
        return df.drop(columns=['total_wins'])

# ==========================================
# 🎨 STREAMLIT INTERFACE
# ==========================================
st.set_page_config(page_title="Fadu MMR Engine v1.4", layout="wide", page_icon="🏸")

if 'clean_logs' not in st.session_state:
    st.session_state.clean_logs = ""

with st.sidebar:
    st.header("⚙️ Status & Diagnostics")
    
    # Sheets Status
    if BRIDGE_URL == "NOT_CONFIGURED": st.error("Sheets Registry: 🔴")
    else: st.success("Sheets Registry: 🟢 Connected")
    
    # AI Heartbeat
    if GEMINI_API_KEY == "NOT_CONFIGURED": 
        st.error("AI Sanitizer: 🔴 (Missing Key)")
    else:
        test_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest?key={GEMINI_API_KEY}"
        try:
            r = requests.get(test_url)
            if r.status_code == 200: st.success("AI Sanitizer: 🟢 Connected")
            else:
                st.error(f"AI: 🟡 Error {r.status_code}")
                st.caption(f"Details: {r.json().get('error', {}).get('message', 'Key mismatch')}")
        except Exception as e:
            st.error("AI Sanitizer: 🟡 Network Issue")
            st.caption(str(e))

    st.divider()
    st.markdown("### 🏷️ League Brackets")
    st.caption("Mythic Glory: 2750+ | Legend: 1900-2299 | Epic: 1650-1899")

st.title("🏸 Fadu Badminton Power Rankings")
st.markdown("Automated MMR tracker with Dynamic Roster building.")

logs_input = st.text_area("Paste Raw Match Logs:", value=st.session_state.clean_logs, height=350, placeholder="Example: 20-Feb\nGame 1: W: VJ, Pacs | L: Jersh, Kenmore")

c1, c2, _ = st.columns([1, 1, 4])
with c1:
    if st.button("✨ AI Sanitize", type="secondary", use_container_width=True):
        if not logs_input:
            st.warning("Please paste messy logs first.")
        else:
            with st.spinner("AI is scrubbing and reformatting..."):
                st.session_state.clean_logs = ai_sanitize_logs(logs_input)
                st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not logs_input:
            st.warning("Nothing to calculate.")
        else:
            with st.spinner("Analyzing stats..."):
                try:
                    engine = FaduMMREngine(ELITE_START)
                    leaderboard = engine.simulate(logs_input)
                    st.subheader("🏆 Leaderboard Results")
                    st.dataframe(leaderboard, use_container_width=True, hide_index=True)
                    
                    if BRIDGE_URL != "NOT_CONFIGURED":
                        payload = {"target": "Registry", "headers": leaderboard.columns.tolist(), "values": leaderboard.values.tolist()}
                        requests.post(BRIDGE_URL, json=payload)
                        st.balloons()
                        st.success("✅ Registry synced to Google Sheets!")
                except Exception as e:
                    st.error(f"Engine Error: {str(e)}")

st.divider()
st.caption("Fadu MMR Engine v1.4 | Powered by REST AI & Python")import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
import json

# ==========================================
# ⚙️ CONFIGURATION & HEADSTARTS
# ==========================================
# Veterans start at 1500 MMR. Everyone else found in the logs starts at 1000.
ELITE_START = [
    "Kenmore", "Lance", "Sam", "Jerome", "Pacs", "VJ", "Luke", 
    "Kent", "Ivan", "Efren", "Jayson", "Allen", "Bombi", "AJ"
]

# Securely fetch secrets from Streamlit Cloud
try:
    BRIDGE_URL = st.secrets["BRIDGE_URL"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    BRIDGE_URL = "NOT_CONFIGURED"
    GEMINI_API_KEY = "NOT_CONFIGURED"

# ==========================================
# ✨ STABLE AI SANITIZER (REST API)
# ==========================================
def ai_sanitize_logs(raw_input):
    if GEMINI_API_KEY == "NOT_CONFIGURED":
        return "ERROR: Missing API Key in Streamlit Secrets."
    
    # Path updated to v1beta/models/...-latest to solve the 404/NOT_FOUND issue
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    You are a Master Data Parser for the Fadu Badminton League.
    
    TASK:
    Transform messy, conversational game logs into a strict programmatic format.
    
    RULES:
    1. OUTPUT FORMAT: 'Game X: W: Winner1, Winner2 | L: Loser1, Loser2'
    2. FOOLPROOF MAPPING: Even if the input is a sentence like 'Kim, Lea vs Fadu, Mitch: WINNER - FADU, MITCH', you MUST identify that Fadu/Mitch are winners and Kim/Lea are losers.
    3. DATE HEADERS: Keep lines like '20-Feb' or '07-Mar' exactly as they are.
    4. NO CONVERSATION: Return ONLY the cleaned data without any preamble.
    
    INPUT TO PROCESS:
    {raw_input}
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15)
        res_json = response.json()
        if "candidates" in res_json:
            return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return f"AI Error: {res_json.get('error', {}).get('message', 'Check API Key Status.')}"
    except Exception as e:
        return f"Request Error: {str(e)}"

# ==========================================
# 🧠 DYNAMIC MMR ENGINE v4.32 (FULL LOGIC)
# ==========================================
class FaduMMREngine:
    def __init__(self, elite_list):
        self.elite_list = [n.strip().lower() for n in elite_list]
        self.players = {}

    def get_player(self, name):
        name_clean = name.strip()
        name_lower = name_clean.lower()
        if name_lower not in self.players:
            # Dynamic Seeding: Elite list gets 1500, others 1000
            start_mmr = 1500 if name_lower in self.elite_list else 1000
            self.players[name_lower] = {
                'display_name': name_clean,
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
                'active_this_session': False
            }
        return name_lower

    def get_tier(self, mmr):
        if mmr < 1349: return "Master"
        elif mmr < 1649: return "Grandmaster"
        elif mmr < 1899: return "Epic"
        elif mmr < 2299: return "Legend"
        elif mmr < 2749: return "Mythic"
        return "Mythical Glory"

    def generate_power_remark(self, p, apd, aod, elite_thresh, rank):
        """Official Fadu AI Commentary Logic."""
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
        
        all_dates = list(dict.fromkeys([l['date'] for l in structured_logs]))
        last_session_idx = len(all_dates) - 1

        for idx, date in enumerate(all_dates):
            is_last_session = (idx == last_session_idx)
            session_games = [g for g in structured_logs if g['date'] == date]
            
            # Reset session counters
            for p in self.players.values():
                p['active_this_session'] = False
                p['session_w'] = 0
                p['session_l'] = 0

            for game in session_games:
                win_keys = [self.get_player(n) for n in game['W']]
                lose_keys = [self.get_player(n) for n in game['L']]
                active_mmrs = [p['mmr'] for p in self.players.values()]
                elite_thresh = np.percentile(active_mmrs, 80) if active_mmrs else 1500

                # --- WINNER LOGIC (With Giant Slayer Bonus) ---
                for i, wk in enumerate(win_keys):
                    w = self.players[wk]
                    if not w['active_this_session']:
                        w['mmr_start_of_session'], w['active_this_session'] = w['mmr'], True
                    
                    # Lambda Decay Check
                    eff = 0 if (idx - w['last_session_idx'] >= 4) else (w['wins'] + w['losses'])
                    lam = 0.40 if eff <= 5 else 0.25 if eff <= 15 else 0.15
                    
                    # Giant Slayer Bonus Calc
                    h_opp = max(self.players[lk]['mmr'] for lk in lose_keys)
                    bonus = min((h_opp - w['mmr']) * lam, 80) if w['mmr'] < 1349 and (h_opp - w['mmr']) >= 300 else 0
                    
                    w['mmr'] += (40 + bonus)
                    w['wins'] += 1; w['session_w'] += 1; w['peak'] = max(w['peak'], w['mmr'])
                    w['total_opp_mmr'] += (sum(self.players[lk]['mmr'] for lk in lose_keys) / 2)
                    w['total_partner_mmr_delta'] += (self.players[win_keys[1-i]]['mmr'] - w['mmr'])

                # --- LOSER LOGIC (With Guardian Shields) ---
                for i, lk in enumerate(lose_keys):
                    l = self.players[lk]; partner = self.players[lose_keys[1-i]]
                    if not l['active_this_session']:
                        l['mmr_start_of_session'], l['active_this_session'] = l['mmr'], True
                    
                    # Rookie Shield
                    loss = 10 if (l['wins'] + l['losses']) < 5 else 20
                    
                    # Guardian Shield (Elite Carry or Partner Subsidy)
                    gap = l['mmr'] - partner['mmr']
                    if l['mmr'] >= elite_thresh and gap >= 150:
                        loss = 16 if gap < 300 else 12 if gap < 500 else 8
                    elif partner['mmr'] >= elite_thresh and (partner['mmr'] - l['mmr']) >= 150:
                        loss = 16
                    
                    l['mmr'] -= loss; l['losses'] += 1; l['session_l'] += 1
                    l['total_opp_mmr'] += (sum(self.players[wk]['mmr'] for wk in win_keys) / 2)
                    l['total_partner_mmr_delta'] += (partner['mmr'] - l['mmr'])

            if not is_last_session:
                for p in self.players.values():
                    if p['active_this_session']:
                        p['is_new_to_league'] = False
                        p['last_session_idx'] = idx

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
        
        # Apply Power Remarks
        df["Power Remarks"] = df.apply(lambda row: self.generate_power_remark(
            self.players[row['Player'].lower()], row['Avg Partner Delta'], 
            row['Avg Opponent MMR'], elite_thresh, row['Rank']), axis=1
        )
        
        return df.drop(columns=['total_wins'])

# ==========================================
# 🎨 STREAMLIT INTERFACE
# ==========================================
st.set_page_config(page_title="Fadu MMR Engine v1.4", layout="wide", page_icon="🏸")

if 'clean_logs' not in st.session_state:
    st.session_state.clean_logs = ""

with st.sidebar:
    st.header("⚙️ Status & Diagnostics")
    
    # Sheets Status
    if BRIDGE_URL == "NOT_CONFIGURED": st.error("Sheets Registry: 🔴")
    else: st.success("Sheets Registry: 🟢 Connected")
    
    # AI Heartbeat
    if GEMINI_API_KEY == "NOT_CONFIGURED": 
        st.error("AI Sanitizer: 🔴 (Missing Key)")
    else:
        test_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest?key={GEMINI_API_KEY}"
        try:
            r = requests.get(test_url)
            if r.status_code == 200: st.success("AI Sanitizer: 🟢 Connected")
            else:
                st.error(f"AI: 🟡 Error {r.status_code}")
                st.caption(f"Details: {r.json().get('error', {}).get('message', 'Key mismatch')}")
        except Exception as e:
            st.error("AI Sanitizer: 🟡 Network Issue")
            st.caption(str(e))

    st.divider()
    st.markdown("### 🏷️ League Brackets")
    st.caption("Mythic Glory: 2750+ | Legend: 1900-2299 | Epic: 1650-1899")

st.title("🏸 Fadu Badminton Power Rankings")
st.markdown("Automated MMR tracker with Dynamic Roster building.")

logs_input = st.text_area("Paste Raw Match Logs:", value=st.session_state.clean_logs, height=350, placeholder="Example: 20-Feb\nGame 1: W: VJ, Pacs | L: Jersh, Kenmore")

c1, c2, _ = st.columns([1, 1, 4])
with c1:
    if st.button("✨ AI Sanitize", type="secondary", use_container_width=True):
        if not logs_input:
            st.warning("Please paste messy logs first.")
        else:
            with st.spinner("AI is scrubbing and reformatting..."):
                st.session_state.clean_logs = ai_sanitize_logs(logs_input)
                st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not logs_input:
            st.warning("Nothing to calculate.")
        else:
            with st.spinner("Analyzing stats..."):
                try:
                    engine = FaduMMREngine(ELITE_START)
                    leaderboard = engine.simulate(logs_input)
                    st.subheader("🏆 Leaderboard Results")
                    st.dataframe(leaderboard, use_container_width=True, hide_index=True)
                    
                    if BRIDGE_URL != "NOT_CONFIGURED":
                        payload = {"target": "Registry", "headers": leaderboard.columns.tolist(), "values": leaderboard.values.tolist()}
                        requests.post(BRIDGE_URL, json=payload)
                        st.balloons()
                        st.success("✅ Registry synced to Google Sheets!")
                except Exception as e:
                    st.error(f"Engine Error: {str(e)}")

st.divider()
st.caption("Fadu MMR Engine v1.4 | Powered by REST AI & Python")