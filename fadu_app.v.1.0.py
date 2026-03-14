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
# Veteran players who receive a seeded start of 1500 MMR.
# All other players discovered dynamically in the logs start at 1000 MMR.
ELITE_START = [
    "Kenmore", "Lance", "Sam", "Jerome", "Pacs", "VJ", "Luke", 
    "Kent", "Ivan", "Efren", "Jayson", "Allen", "Bombi", "AJ"
]

# Official Tier Thresholds as defined in the Fadu Operations Manual.
TIERS = {
    "Mythical Glory": 2750,
    "Mythic": 2300,
    "Legend": 1900,
    "Epic": 1650,
    "Grandmaster": 1350,
    "Master": 0
}

# Fetch Secure Secrets from Streamlit Cloud Environment
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
    /* Main Background and Container */
    .main { background-color: #f8f9fb; }
    
    /* Dataframe Styling */
    .stDataFrame { 
        border: 1px solid #e6e9ef; 
        border-radius: 12px; 
        overflow: hidden; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.05); 
    }
    
    /* Metrics Styling */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e6e9ef;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e6e9ef;
    }
    
    /* Custom Header Color */
    h1, h2, h3 { color: #1e293b; font-weight: 700; }
    
    /* Button Hover Effects */
    .stButton>button {
        border-radius: 8px;
        transition: all 0.2s ease-in-out;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# ✨ ADVANCED AI SANITIZER (STABLE REST API)
# ==========================================
def ai_sanitize_logs(raw_input):
    """
    Leverages Gemini 1.5 Flash to parse conversational badminton logs.
    Targets messy human input and converts it to strict W/L logic.
    """
    if GEMINI_API_KEY == "NOT_CONFIGURED":
        return "ERROR: Missing API Key in Streamlit Secrets."
    
    # Path updated to v1beta to ensure support for gemini-1.5-flash-latest
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    You are a Master Data Parser for the Fadu Badminton League. 
    Your goal is to transform messy, human-written logs into a rigid programmatic format for an MMR Engine.

    OFFICIAL ROSTER FOR REFERENCE: {ELITE_START}

    STRICT RULES:
    1. OUTPUT FORMAT: Each game MUST be 'Game X: W: P1, P2 | L: P3, P4'
    2. CONTEXTUAL LOGIC: Identify winners and losers even if written as a sentence.
       - Example: 'Kim, Lea vs Fadu, Mitch: WINNER - FADU, MITCH'
       - Result: 'W: Fadu, Mitch | L: Kim, Lea'
    3. DATE PRESERVATION: Keep Date Header lines (e.g. '20-Feb', '14-Mar') exactly as they are.
    4. NAME CONSISTENCY: Map nicknames or variations to the official names in the roster if possible.
    5. NO PREAMBLE: Do not include any conversational text. Return ONLY the cleaned logs.
    6. VALIDATION: If a game is incomprehensible, add '!! CHECK: Missing Data' below it.

    INPUT LOGS TO PROCESS:
    {raw_input}
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.95,
            "maxOutputTokens": 2048,
        }
    }
    headers = {'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=25)
        response.raise_for_status()
        res_json = response.json()
        
        if "candidates" in res_json:
            cleaned_text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            return cleaned_text
        else:
            return f"AI Error: API Response missing candidates. Details: {res_json}"
            
    except requests.exceptions.HTTPError as http_err:
        return f"HTTP Error: {http_err} - Check if your API Key has Gemini Flash access."
    except Exception as e:
        return f"Request Error: {str(e)}"

# ==========================================
# 🧠 DYNAMIC MMR ENGINE v4.5 (MODULAR ARCHITECTURE)
# ==========================================
class FaduMMREngine:
    def __init__(self, elite_list):
        self.elite_list = [n.strip().lower() for n in elite_list]
        self.players = {}
        self.session_data = []

    def get_player(self, name):
        """Initializes a player profile if not found, otherwise returns unique key."""
        n_clean = name.strip()
        n_lower = n_clean.lower()
        
        if n_lower not in self.players:
            # Seeded Start Check
            start_mmr = 1500 if n_lower in self.elite_list else 1000
            self.players[n_lower] = {
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
                'win_streak': 0
            }
        return n_lower

    def get_tier(self, mmr):
        """Returns the rank name based on MMR value."""
        for tier, threshold in TIERS.items():
            if mmr >= threshold: return tier
        return "Master"

    def generate_power_remark(self, p, apd, aod, elite_thresh, rank):
        """High-resolution logic to generate AI commentary for players."""
        # 1. Rookie Logic
        if p.get('is_new_to_league', False) and p['active_this_session']:
            return f"Welcome! Rookie debut with {p['session_w']}-{p['session_l']} record."
        
        # 2. Ranking Logic
        if rank == 1: return "The Final Boss. Absolute League Dominance."
        if rank <= 3: return "Elite Tier. Consistency at the highest level."
        
        # 3. Performance Streaks
        if p['win_streak'] >= 3: return f"On Fire! {p['win_streak']} Game Win Streak."
        if p['session_w'] >= 3 and p['session_l'] == 0: return "Perfect Session. Unstoppable."
        
        # 4. Tactical Anchors
        if apd < -250: return "The Anchor. Carrying the partnership weight."
        if aod > 1650: return "Iron Man. Battling the league heavyweights."
        
        # 5. Peak Performance
        if p['mmr'] >= p['peak'] - 10 and p['wins'] > 10: return "Career High. Playing their best badminton yet."
        
        # 6. Tough Sessions
        if p['session_l'] >= 3: return "Rough Night. The grind continues next session."
        
        return "Pure Hustle. A consistent force on the court."

    def simulate(self, raw_log_text):
        """Main processing loop for MMR calculations across all sessions."""
        structured_logs = self.parse_raw_logs(raw_log_text)
        if not structured_logs: return pd.DataFrame()
        
        # Determine Session Dates
        all_dates = list(dict.fromkeys([l['date'] for l in structured_logs]))
        last_session_idx = len(all_dates) - 1

        for session_idx, date in enumerate(all_dates):
            is_last_session = (session_idx == last_session_idx)
            session_games = [g for g in structured_logs if g['date'] == date]
            
            # Reset Session-Specific Stats
            for p in self.players.values():
                p['active_this_session'] = False
                p['session_w'] = 0
                p['session_l'] = 0

            for game in session_games:
                win_keys = [self.get_player(n) for n in game['W']]
                lose_keys = [self.get_player(n) for n in game['L']]
                
                # Dynamic Elite Threshold Calculation (Top 20% of current pool)
                current_mmrs = [p['mmr'] for p in self.players.values()]
                elite_thresh = np.percentile(current_mmrs, 80) if current_mmrs else 1500

                # --- WINNER CALCULATIONS ---
                for i, wk in enumerate(win_keys):
                    w = self.players[wk]
                    if not w['active_this_session']:
                        w['mmr_start_of_session'], w['active_this_session'] = w['mmr'], True
                    
                    # 1. Lambda Inactivity Decay Logic
                    eff_games = 0 if (session_idx - w['last_session_idx'] >= 4) else (w['wins'] + w['losses'])
                    lam = 0.40 if eff_games <= 5 else 0.25 if eff_games <= 15 else 0.15
                    
                    # 2. Giant Slayer Bonus Logic
                    opp_mmrs = [self.players[lk]['mmr'] for lk in lose_keys]
                    highest_opp = max(opp_mmrs) if opp_mmrs else 1000
                    bonus = 0
                    if w['mmr'] < 1349 and (highest_opp - w['mmr']) >= 300:
                        bonus = min((highest_opp - w['mmr']) * lam, 80)
                    
                    w['mmr'] += (40 + bonus)
                    w['wins'] += 1
                    w['session_w'] += 1
                    w['win_streak'] += 1
                    w['peak'] = max(w['peak'], w['mmr'])
                    
                    # 3. Dynamic Delta Tracking
                    w['total_opp_mmr'] += (sum(opp_mmrs) / 2)
                    w['total_partner_mmr_delta'] += (self.players[win_keys[1-i]]['mmr'] - w['mmr'])

                # --- LOSER CALCULATIONS ---
                for i, lk in enumerate(lose_keys):
                    l = self.players[lk]
                    partner = self.players[lose_keys[1-i]]
                    
                    if not l['active_this_session']:
                        l['mmr_start_of_session'], l['active_this_session'] = l['mmr'], True
                    
                    # 1. Rookie Shield (Game 1-5 Protection)
                    loss_amt = 10 if (l['wins'] + l['losses']) < 5 else 20
                    
                    # 2. Guardian Shield Logic (Elite Carry/Gap protection)
                    gap = l['mmr'] - partner['mmr']
                    if l['mmr'] >= elite_thresh and gap >= 150:
                        # Elite player carrying lower tier
                        loss_amt = 16 if gap < 300 else 12 if gap < 500 else 8
                    elif partner['mmr'] >= elite_thresh and (partner['mmr'] - l['mmr']) >= 150:
                        # Protection for partner of elite player
                        loss_amt = 16
                    
                    l['mmr'] -= loss_amt
                    l['losses'] += 1
                    l['session_l'] += 1
                    l['win_streak'] = 0
                    
                    # 3. Dynamic Delta Tracking
                    opp_mmrs = [self.players[wk]['mmr'] for wk in win_keys]
                    l['total_opp_mmr'] += (sum(opp_mmrs) / 2)
                    l['total_partner_mmr_delta'] += (partner['mmr'] - l['mmr'])

            # Finalize Session for Player History
            if not is_last_session:
                for p in self.players.values():
                    if p['active_this_session']:
                        p['is_new_to_league'] = False
                        p['last_session_idx'] = session_idx

        return self.generate_leaderboard(elite_thresh if 'elite_thresh' in locals() else 1500)

    def parse_raw_logs(self, text):
        """Parses the cleaned AI logs into structured dictionary format."""
        logs = []
        current_date = "Unknown"
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('!!'): continue
            
            # Match Date Headers (e.g., 20-Feb)
            date_match = re.match(r'^(\d{1,2}-[A-Za-z]+)', line)
            if date_match:
                current_date = date_match.group(1)
            elif 'W:' in line:
                try:
                    parts = line.split('|')
                    w_part = parts[0].split('W:')[1].strip()
                    l_part = parts[1].split('L:')[1].strip()
                    logs.append({
                        'date': current_date,
                        'W': [n.strip() for n in w_part.split(',')],
                        'L': [n.strip() for n in l_part.split(',')]
                    })
                except Exception:
                    continue
        return logs

    def generate_leaderboard(self, elite_thresh):
        """Converts internal player dictionaries into the final display DataFrame."""
        leaderboard_data = []
        
        for key, p in self.players.items():
            total_games = p['wins'] + p['losses']
            if total_games == 0: continue
            
            # Calculate Averages
            aod = round(p['total_opp_mmr'] / total_games)
            apd = round(p['total_partner_mmr_delta'] / total_games)
            
            leaderboard_data.append({
                "Rank": 0,
                "Player": p['display_name'],
                "Tier": self.get_tier(p['mmr']),
                "MMR": round(p['mmr']),
                "Peak": round(p['peak']),
                "Session Change": round(p['mmr'] - p['mmr_start_of_session']) if p['active_this_session'] else 0,
                "Avg Opponent MMR": aod,
                "Avg Partner Delta": apd,
                "Status": "Elite" if p['mmr'] >= elite_thresh else "Stable",
                "Confidence": "⭐⭐⭐" if total_games > 15 else "⭐⭐" if total_games > 5 else "⭐",
                "Record": f"{p['wins']}-{p['losses']}",
                "Session": f"{p['session_w']}-{p['session_l']}",
                "wins_for_sorting": p['wins']
            })
            
        # Create DataFrame and Sort
        df = pd.DataFrame(leaderboard_data).sort_values(by=["MMR", "wins_for_sorting"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        
        # Apply Power Remarks
        df["Power Remarks"] = df.apply(lambda row: self.generate_power_remark(
            self.players[row['Player'].lower()], row['Avg Partner Delta'], 
            row['Avg Opponent MMR'], elite_thresh, row['Rank']), axis=1
        )
        
        return df.drop(columns=['wins_for_sorting'])

# ==========================================
# 📊 STREAMLIT DASHBOARD UI
# ==========================================
st.set_page_config(page_title="Fadu MMR Engine v1.7", layout="wide", page_icon="🏸")

# App Initialization State
if 'cleaned_logs_state' not in st.session_state:
    st.session_state.cleaned_logs_state = ""

# --- Sidebar Configuration ---
with st.sidebar:
    st.image("https://img.icons8.com/color/96/badminton.png", width=80)
    st.title("Fadu League Ops")
    st.markdown("---")
    
    # Connection Diagnostics
    st.subheader("System Health")
    
    # 1. Google Sheets Registry Status
    if BRIDGE_URL != "NOT_CONFIGURED":
        st.success("Sheets Registry: 🟢 CONNECTED")
    else:
        st.error("Sheets Registry: 🔴 DISCONNECTED")
        st.caption("Check Streamlit 'Secrets' for BRIDGE_URL.")
    
    # 2. AI Sanitizer (REST API) Heartbeat
    if GEMINI_API_KEY != "NOT_CONFIGURED":
        # Testing the v1beta endpoint specifically
        hb_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest?key={GEMINI_API_KEY}"
        try:
            hb_resp = requests.get(hb_url, timeout=5)
            if hb_resp.status_code == 200:
                st.success("AI Sanitizer: 🟢 READY")
            else:
                st.error(f"AI Sanitizer: 🟡 ERROR {hb_resp.status_code}")
                st.caption(f"Reason: {hb_resp.json().get('error', {}).get('message', 'Check key access.')}")
        except Exception:
            st.error("AI Sanitizer: 🔴 OFFLINE")
    else:
        st.error("AI Sanitizer: 🔴 NO KEY FOUND")

    st.markdown("---")
    st.subheader("League Brackets")
    st.info("**Mythical Glory**: 2750+\n\n**Mythic**: 2300-2749\n\n**Legend**: 1900-2299\n\n**Epic**: 1650-1899\n\n**Grandmaster**: 1350-1649\n\n**Master**: Below 1350")
    
    st.divider()
    st.caption(f"Fadu Engine v1.7 | {datetime.now().strftime('%Y-%m-%d')}")

# --- Main Interface ---
st.title("🏸 Fadu Badminton Power Rankings")
st.markdown("Automated MMR Calculation and Registry Management System.")

# 1. Raw Data Input Area
input_logs = st.text_area(
    "Paste Raw Match Logs (from Facebook/Chat):", 
    value=st.session_state.cleaned_logs_state, 
    height=350,
    placeholder="Example:\n20-Feb\nGame 1: Kim, Mitch beat Pacs, Lance..."
)

# 2. Action Controls
col1, col2, col3 = st.columns([1.5, 1.5, 4])

with col1:
    if st.button("✨ AI Sanitize Logs", type="secondary", use_container_width=True):
        if not input_logs:
            st.warning("Please paste raw logs first.")
        else:
            with st.spinner("AI is parsing, fixing typos, and reformatting..."):
                start_time = time.time()
                cleaned_result = ai_sanitize_logs(input_logs)
                st.session_state.cleaned_logs_state = cleaned_result
                end_time = time.time()
                st.toast(f"Logs Sanitized in {round(end_time - start_time, 1)}s", icon="✨")
                st.rerun()

with col2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not input_logs:
            st.warning("No logs provided for calculation.")
        else:
            with st.spinner("Executing MMR Algorithms and Syncing..."):
                try:
                    # 1. Initialize Engine and Simulate
                    engine = FaduMMREngine(ELITE_START)
                    leaderboard = engine.simulate(input_logs)
                    
                    # 2. Display Result Table
                    st.divider()
                    st.subheader("🏆 Official Leaderboard Results")
                    st.dataframe(
                        leaderboard, 
                        use_container_width=True, 
                        hide_index=True
                    )
                    
                    # 3. Handle Cloud Sync
                    if BRIDGE_URL != "NOT_CONFIGURED":
                        sync_payload = {
                            "target": "Registry", 
                            "headers": leaderboard.columns.tolist(), 
                            "values": leaderboard.values.tolist()
                        }
                        sync_resp = requests.post(BRIDGE_URL, json=sync_payload, timeout=15)
                        
                        if sync_resp.status_code == 200:
                            st.balloons()
                            st.success(f"✅ Google Sheets Registry updated successfully at {datetime.now().strftime('%H:%M:%S')}!")
                        else:
                            st.error(f"Sync failed. Google says: {sync_resp.text}")
                    else:
                        st.info("Sync Skipped: No BRIDGE_URL configured in Secrets.")
                        
                except Exception as e:
                    st.error(f"Critical System Error: {str(e)}")

# Footer
st.divider()
st.caption("Advanced Badminton Analytics for the Fadu Badminton League.")