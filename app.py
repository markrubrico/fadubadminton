import streamlit as st
import requests
import pandas as pd
import numpy as np
import config # Ensure we import config to access the master list
from engine import FaduMMREngine
from auditor import ai_audit_session

# --- 1. DASHBOARD CONFIGURATION ---
# Milestone: v5.0.0 - Official Public Player Portal Launch
st.set_page_config(
    page_title="Fadu MMR Portal v5.0.0",
    page_icon="🏸",
    layout="wide"
)

# --- 2. DATA BRIDGE: PUBLIC FETCHING ---
@st.cache_data(ttl=600)  # Refreshes public data for players every 10 minutes
def fetch_public_data():
    """Pulls current Registry and Match_History from Published Google Sheet CSVs."""
    reg_url = st.secrets.get("REGISTRY_CSV_URL", "")
    hist_url = st.secrets.get("HISTORY_CSV_URL", "")
    
    try:
        if not reg_url or not hist_url:
            return None, None
        
        lb_df = pd.read_csv(reg_url)
        hist_df = pd.read_csv(hist_url)
        
        # Reconstruct the raw multi-line log string from the Match_History sheet.
        raw_history = "\n".join(hist_df.iloc[:, 0].astype(str).tolist())
        return lb_df, raw_history
    except Exception:
        return None, None

# --- 3. SIDEBAR STATUS & ACCESS CONTROL ---
with st.sidebar:
    st.title("🏸 Fadu Ops")
    
    # 🔐 ADMIN ACCESS GATE
    ops_key = st.text_input("Admin Access Key", type="password", help="Enter key to enable Calculation & Sync tools.")
    is_admin = (ops_key == st.secrets.get("OPS_PASSWORD", "fadu2026"))
    
    if is_admin:
        st.success("👨‍⚖️ Admin Mode: Authorized")
        sync_enabled = st.checkbox("Enable Cloud Sync", value=True)
        
        st.divider()
        
        # Admin-Only Connection Indicators
        if "BRIDGE_URL" in st.secrets:
            st.success("Registry: 🟢 Online")
        else:
            st.error("Registry: 🔴 Offline")
            
        st.markdown("### 📊 Data Source")
        st.markdown("[🔗 Open Official Google Registry](https://docs.google.com/spreadsheets/d/1mPd-WUmyrwC5MEtBbADzyTmJJpOqr7MZPueloFUYyHo/edit?usp=sharing)")
        
        if "GROQ_API_KEY" in st.secrets:
            st.success("AI Auditor: 🟢 Online")
        else:
            st.error("AI Auditor: 🔴 Offline")
            
    else:
        st.info("👋 Player Mode: Read-Only")

    st.divider()

    # VIEW FILTERS (Visible to everyone)
    st.subheader("🎯 View Filters")
    hide_inactive = st.checkbox("Hide Inactive", value=False, help="Removes players with 4+ missed sessions.")
    hide_rookies = st.checkbox(f"Hide Rookies (< {config.ROOKIE_SHIELD_GAMES} games)", value=False)
    show_present_only = st.checkbox("Show last session only", value=False)

    # DYNAMIC HIDDEN COUNT WARNING
    active_lb = st.session_state.get('lb', None)
    if active_lb is not None:
        df_full = active_lb
        required_cols = ['Missed_Sessions', 'Total_Games', 'Is_Present']
        if all(col in df_full.columns for col in required_cols):
            df_temp = df_full.copy()
            if hide_inactive: df_temp = df_temp[df_temp['Missed_Sessions'] < 4]
            if hide_rookies: df_temp = df_temp[df_temp['Total_Games'] >= config.ROOKIE_SHIELD_GAMES]
            if show_present_only: df_temp = df_temp[df_temp['Is_Present'] == True]
            hidden_count = len(df_full) - len(df_temp)
            if hidden_count > 0: st.warning(f"🚫 Players Hidden: {hidden_count}")

    st.divider()
    with st.expander("💠 Initial Seeded Roster"):
        st.caption("v4.5/v5.0 Veteran Seed List (1500 MMR Start):")
        seed_string = ", ".join(config.SEEDS)
        st.write(f"**{seed_string}**")
    
    st.divider()
    st.caption("v5.0.0 | Portal Launch Build")
    st.info("📍 Manila, PH")

# --- 4. DATA LOADING ---
public_lb, public_logs = fetch_public_data()

# --- 5. ADMIN VIEW: COMMISSIONER CONSOLE ---
if is_admin:
    st.title("🛠️ Commissioner Console")
    st.markdown("Automated MMR processing with double-target Sync (Registry + Match_History).")

    input_area = st.text_area(
        "Match Logs Input (Full History):", 
        height=200, 
        placeholder="Paste your chronological logs here...",
        value=st.session_state.get('last_input', "")
    )

    c1, c2, _ = st.columns([1.5, 1.5, 4])

    with c1:
        if st.button("🔍 Run Session Audit", width='stretch'):
            if not input_area.strip(): st.warning("Please paste logs first.")
            else:
                with st.spinner("Checking logs..."):
                    engine = FaduMMREngine()
                    engine.simulate(input_area) 
                    report = ai_audit_session(input_area, list(engine.players.keys()))
                    st.session_state.audit_report = report

    with c2:
        if st.button("🚀 Calculate & Sync", type="primary", width='stretch'):
            if not input_area.strip(): st.warning("Please paste logs first.")
            else:
                with st.spinner("Syncing Major Update..."):
                    engine = FaduMMREngine()
                    df, last_date, drift, decayed = engine.simulate(input_area)
                    st.session_state.lb, st.session_state.drift = df, drift
                    st.session_state.date, st.session_state.decayed = last_date, decayed 
                    st.session_state.admin_logs = input_area
                    
                    if sync_enabled and "BRIDGE_URL" in st.secrets:
                        payload_lb = {"target": "Registry", "headers": df.columns.tolist(), "values": df.values.tolist()}
                        log_lines = [[line] for line in input_area.split('\n')]
                        payload_hist = {"target": "Match_History", "headers": ["Raw_Logs"], "values": log_lines}
                        
                        try:
                            requests.post(st.secrets["BRIDGE_URL"], json=payload_lb, timeout=20)
                            requests.post(st.secrets["BRIDGE_URL"], json=payload_hist, timeout=20)
                            st.success("🎉 Global Registry & Match History Updated!")
                            st.cache_data.clear()
                        except:
                            st.error("Sync Failed")

    if 'audit_report' in st.session_state:
        st.info(f"### 📋 Audit Findings\n{st.session_state.audit_report}")
        if st.button("Close Audit"): del st.session_state.audit_report; st.rerun()

# --- 6. PLAYER HUB: THE ELITE EXPERIENCE ---
st.divider()
st.title("🏆 Fadu Badminton Portal")

# Source of Truth routing
if is_admin and 'lb' in st.session_state:
    display_lb, display_logs = st.session_state.lb, st.session_state.get('admin_logs', "")
else:
    display_lb, display_logs = public_lb, public_logs

if display_lb is not None:
    # --- HEATMAP DECAY ALERT ---
    if is_admin and st.session_state.get('decayed'):
        with st.expander("📉 Inactivity Decay Alert", expanded=True):
            decay_df = pd.DataFrame(st.session_state.decayed)
            st.dataframe(decay_df.style.map(lambda v: 'background-color: #c0392b; color: white' if v > 4 else 'background-color: #e67e22; color: white', subset=['Missed']), width='stretch', hide_index=True)

    tab1, tab2 = st.tabs(["📊 Hall of Fame & Rankings", "⚔️ Combat & Progression"])

    # --- TAB 1: HALL OF FAME & LEADERBOARD ---
    with tab1:
        st.subheader("🌟 Session Highlights")
        h1, h2, h3, h4 = st.columns(4)
        
        # MVP Logic (+/-)
        if '+/-' in display_lb.columns:
            mvp_row = display_lb.loc[display_lb['+/-'].idxmax()]
            h1.metric("🔥 Session MVP", mvp_row['Player'], f"+{mvp_row['+/-']} MMR")
            
        # Hard Carry Logic (APD)
        if 'APD' in display_lb.columns:
            carry_row = display_lb.loc[display_lb['APD'].idxmax()]
            h2.metric("🏋️ Hard Carry", carry_row['Player'], f"{carry_row['APD']} APD")

        # Iron Man Logic (Games Played Today)
        if 'Last Session' in display_lb.columns:
            def calc_total(val):
                try: return sum([int(i) for i in str(val).split('-')])
                except: return 0
            display_lb['Total_Today'] = display_lb['Last Session'].apply(calc_total)
            iron_row = display_lb.loc[display_lb['Total_Today'].idxmax()]
            h3.metric("🦾 Iron Man", iron_row['Player'], f"{iron_row['Total_Today']} Games")
        
        h4.metric("📈 League Average", f"{int(display_lb['MMR'].mean())}", "Balanced")

        st.divider()
        
        # Leaderboard
        if is_admin: st.metric("Session Wealth Drift", f"{st.session_state.drift} MMR")
        search = st.text_input("🔍 Search Player:", placeholder="Filter by name...")
        df_disp = display_lb.copy()
        if search: df_disp = df_disp[df_disp['Player'].str.contains(search, case=False)]
        if hide_inactive: df_disp = df_disp[df_disp['Missed_Sessions'] < 4]
        if hide_rookies: df_disp = df_disp[df_disp['Total_Games'] >= config.ROOKIE_SHIELD_GAMES]
        if show_present_only: df_disp = df_disp[df_disp['Is_Present'] == True]
        
        cols = [c for c in df_disp.columns if c not in ["Total_Games", "Missed_Sessions", "Is_Present", "Total_Today"]]
        st.dataframe(df_disp[cols], width='stretch', hide_index=True)

    # --- TAB 2: COMBAT & PROGRESSION ---
    with tab2:
        player_list = sorted(display_lb['Player'].tolist())
        hero = st.selectbox("Select Player Profile:", player_list)
        st.divider()
        col_p1, col_p2 = st.columns(2)
        engine = FaduMMREngine()
        
        with col_p1:
            # TIER PROGRESSION (Road to Mythic)
            st.subheader("🛡️ Road to Mythic")
            current_mmr = display_lb.loc[display_lb['Player'] == hero, 'MMR'].values[0]
            
            tiers = [("Master", 1000), ("Grandmaster", 1500), ("Epic", 1900), 
                     ("Legend", 2300), ("Mythic", 2700), ("Mythic Glory", 3200)]
            
            curr_tier, next_tier, next_mmr = "Master", "Grandmaster", 1500
            for name, val in tiers:
                if current_mmr >= val: curr_tier = name
                else: 
                    next_tier, next_mmr = name, val
                    break
            
            floor_mmr = tiers[[t[0] for t in tiers].index(curr_tier)][1]
            prog = (current_mmr - floor_mmr) / (next_mmr - floor_mmr)
            st.write(f"**Rank:** {curr_tier} | **Next Goal:** {next_tier}")
            st.progress(min(max(prog, 0.0), 1.0))
            st.caption(f"🚀 **{int(next_mmr - current_mmr)} MMR** to go.")

            st.divider()
            
            # RIVALRY RADAR
            st.subheader("📡 Rivalry Radar")
            riv_df = engine.get_rivalry_matrix(display_logs, hero)
            if riv_df is not None:
                nemesis_df = riv_df[riv_df['Games'] >= 2].sort_values(by='Win%')
                if not nemesis_df.empty:
                    nem = nemesis_df.iloc[0]
                    st.error(f"⚠️ **Nemesis:** {nem['Opponent']} (Win rate vs them: {nem['Win%']}%)")
                
                syn_df = engine.get_teammate_matrix(display_logs, hero)
                if syn_df is not None:
                    duo_df = syn_df[syn_df['Games'] >= 2].sort_values(by='Win%', ascending=False)
                    if not duo_df.empty:
                        duo = duo_df.iloc[0]
                        st.success(f"🤝 **Dynamic Duo:** Strongest chemistry with {duo['Partner']} ({duo['Win%']}% Win rate)")

        with col_p2:
            st.subheader("🔋 Stamina Analysis")
            if st.button(f"Analyze {hero}'s Fatigue Curve", width='stretch'):
                s_df = engine.get_stamina_analysis(display_logs, hero)
                if s_df is not None: st.dataframe(s_df, width='stretch', hide_index=True)
            
            st.divider()
            st.subheader("📊 Opponent Career Matrix")
            if st.button(f"Generate Career Rivals for {hero}", width='stretch'):
                riv_full = engine.get_rivalry_matrix(display_logs, hero)
                if riv_full is not None: st.dataframe(riv_full, width='stretch', hide_index=True)
            
            st.divider()
            st.subheader("⚔️ Head-to-Head")
            rival = st.selectbox("Compare vs Rival:", player_list)
            if st.button("Analyze Direct H2H", width='stretch'):
                h2h = engine.get_h2h(display_logs, hero, rival)
                if h2h and h2h["matches"]:
                    st.write(f"### {hero} {h2h['p1_wins']} - {h2h['p2_wins']} {rival}")
                    st.table(pd.DataFrame(h2h["matches"]))
else:
    st.warning("⚠️ Waiting for Registry Sync...")

st.divider()
st.caption("v5.0.0 | Fadu Badminton Portal | Manila 2026")