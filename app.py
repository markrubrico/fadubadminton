import streamlit as st
import requests
import pandas as pd
import numpy as np
import config # Ensure we import config to access the master list
from engine import FaduMMREngine
from auditor import ai_audit_session

# --- 1. DASHBOARD CONFIGURATION ---
# Milestone: v5.4.3 - Rankings Restoration & Hero Card Migration
st.set_page_config(
    page_title="Fadu & Friends Portal v5.4.3",
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
        
        # Pull the current Leaderboard
        lb_df = pd.read_csv(reg_url)
        
        # Pull the Raw Match Logs
        hist_df = pd.read_csv(hist_url)
        
        # Reconstruct history logs correctly.
        valid_logs = hist_df.iloc[:, 0].dropna().astype(str).tolist()
        if valid_logs and "Raw_Logs" in valid_logs[0]:
            valid_logs = valid_logs[1:]
            
        raw_history = "\n".join(valid_logs)
        return lb_df, raw_history
    except Exception:
        return None, None

# --- 3. SIDEBAR STATUS & ACCESS CONTROL ---
with st.sidebar:
    st.title("🏸 Fadu Ops")
    
    # 🔐 ADMIN ACCESS GATE
    ops_key = st.text_input("Admin Access Key", type="password", help="Unlock Commissioner Console.")
    is_admin = (ops_key == st.secrets.get("OPS_PASSWORD", "fadu2026"))
    
    if is_admin:
        st.success("👨‍⚖️ Admin Mode: Authorized")
        sync_enabled = st.checkbox("Enable Cloud Sync", value=True, help="If unchecked, calculations stay local.")
        
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
        st.caption("v5.1 Veteran Seed List (1500 MMR Start):")
        seed_string = ", ".join(config.SEEDS)
        st.write(f"**{seed_string}**")
    
    st.divider()
    st.caption("v5.4.3 | Community Edition")
    st.info("📍 Manila, PH")

# --- 4. MOBILE NUDGE & DATA LOADING ---
if not is_admin:
    st.info("👈 **Mobile Users:** Tap the arrow in the top-left to filter rankings or access player profiles.")

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
                        # SYNC LOCK: Payload uses the unabridged 19-column Engine output
                        payload_lb = {"target": "Registry", "headers": df.columns.tolist(), "values": df.values.tolist()}
                        log_lines = [[line] for line in input_area.split('\n')]
                        payload_hist = {"target": "Match_History", "headers": ["Raw_Logs"], "values": log_lines}
                        
                        try:
                            requests.post(st.secrets["BRIDGE_URL"], json=payload_lb, timeout=20)
                            requests.post(st.secrets["BRIDGE_URL"], json=payload_hist, timeout=20)
                            st.success("🎉 Global Registry & History Updated!")
                            st.cache_data.clear()
                        except:
                            st.error("Sync Failed")

    if 'audit_report' in st.session_state:
        st.info(f"### 📋 Audit Findings\n{st.session_state.audit_report}")
        if st.button("Close Audit"): del st.session_state.audit_report; st.rerun()

# --- 6. PLAYER HUB ---
st.divider()
st.markdown("### 🏆 Fadu & Friends: Community Rankings")

# Source of Truth routing
if is_admin and 'lb' in st.session_state:
    display_lb, display_logs = st.session_state.lb, st.session_state.get('admin_logs', "")
    session_date = st.session_state.get('date', "Latest")
else:
    display_lb, display_logs = public_lb, public_logs
    if display_logs and len(display_logs) > 10:
        lines = display_logs.split('\n')
        date_lines = [l for l in lines if '-' in l and len(l) < 15]
        session_date = date_lines[0] if date_lines else "Cloud Sync"
    else:
        session_date = "Cloud Sync"

if display_lb is not None:
    # DATA SAFETY LAYER: Force initialization of new stats if missing from CSV
    for col in ["Max Streak", "Underdog Wins", "Archetype"]:
        if col not in display_lb.columns:
            display_lb[col] = 0 if col != "Archetype" else "Consistent Force"

    tab1, tab2, tab3 = st.tabs(["📊 RANKINGS", "⚔️ COMBAT & SYNERGY", "📖 FAQ"])

    # --- TAB 1: RANKINGS ---
    with tab1:
        st.markdown(f"###### 🌟 Session Highlights ({session_date})")
        h1, h2, h3, h4 = st.columns(4)
        
        if '+/-' in display_lb.columns:
            mvp_row = display_lb.loc[display_lb['+/-'].idxmax()]
            h1.metric("🔥 Session MVP", mvp_row['Player'], f"+{mvp_row['+/-']} MMR")
            
        if 'APD' in display_lb.columns:
            carry_row = display_lb.loc[display_lb['APD'].idxmax()]
            h2.metric("🏋️ Hard Carry", carry_row['Player'], f"{carry_row['APD']} APD")

        if 'Last Session' in display_lb.columns:
            def calc_total(val):
                try: 
                    if pd.isna(val) or str(val).strip() == "": return 0
                    return sum([int(i) for i in str(val).split('-')])
                except: return 0
            display_lb['Total_Today'] = display_lb['Last Session'].apply(calc_total)
            iron_row = display_lb.loc[display_lb['Total_Today'].idxmax()]
            h3.metric("🦾 Iron Man", iron_row['Player'], f"{iron_row['Total_Today']} Games")
        
        if 'MMR' in display_lb.columns:
            h4.metric("📈 League Average", f"{int(display_lb['MMR'].mean())}", "Balanced")

        st.divider()
        search = st.text_input("🔍 Search Player:", placeholder="Filter by name...", key="p_search")
        df_disp = display_lb.copy()
        if search: df_disp = df_disp[df_disp['Player'].str.contains(search, case=False)]
        
        if hide_inactive and 'Missed_Sessions' in df_disp.columns: df_disp = df_disp[df_disp['Missed_Sessions'] < 4]
        if hide_rookies and 'Total_Games' in df_disp.columns: df_disp = df_disp[df_disp['Total_Games'] >= config.ROOKIE_SHIELD_GAMES]
        if show_present_only and 'Is_Present' in df_disp.columns: df_disp = df_disp[df_disp['Is_Present'] == True]
        
        # RESTORED: THE ORIGINAL 13 COLUMNS DISPLAY
        original_13 = [
            "Rank", "Player", "Tier", "MMR", "Peak", "+/-", 
            "AOD", "APD", "Status", "Confidence", 
            "Last Session", "Season Record", "Remarks"
        ]
        final_cols = [c for c in original_13 if c in df_disp.columns]
        st.dataframe(df_disp[final_cols], width='stretch', hide_index=True)

    # --- TAB 2: COMBAT & SYNERGY ---
    with tab2:
        player_list = sorted([p.strip() for p in display_lb['Player'].tolist()])
        hero = st.selectbox("Select Player Profile:", player_list)
        st.divider()
        
        engine = FaduMMREngine()
        hero_row = display_lb.loc[display_lb['Player'].str.strip() == hero]
        
        if not hero_row.empty:
            # --- HERO PROFILE HEADER ---
            p_arch = hero_row['Archetype'].values[0]
            st.markdown(f"## {p_arch} : {hero}")
            
            # --- HERO HALL OF FAME CARDS ---
            st.markdown("#### 🏛️ Hall of Fame")
            f1, f2, f3, f4 = st.columns(4)
            f1.metric("🏆 All-Time Peak", f"{int(hero_row['Peak'].values[0])} MMR")
            f2.metric("🔥 Max Win Streak", f"{int(hero_row['Max Streak'].values[0])} Games")
            f3.metric("⚔️ Giants Slayed", f"{int(hero_row['Underdog Wins'].values[0])}", help="Victories vs 300+ MMR gaps.")
            f4.metric("📈 Season Record", hero_row['Season Record'].values[0])

        st.divider()
        col_p1, col_p2 = st.columns(2)
        riv_df = engine.get_rivalry_matrix(display_logs, hero)
        syn_df = engine.get_teammate_matrix(display_logs, hero)
        
        with col_p1:
            st.subheader("🛡️ Road to Mythic")
            if not hero_row.empty:
                current_mmr = hero_row['MMR'].values[0]
                st.write(f"**Current Rank:** {hero_row['Tier'].values[0]}")
                st.progress(min(max((current_mmr - 1000) / 2200, 0.0), 1.0))
                st.caption(f"Current MMR: {int(current_mmr)}")

            st.divider()
            st.subheader("📡 Radar Stats")
            if riv_df is not None and not riv_df.empty:
                nemesis_df = riv_df[riv_df['Total'] >= 2].sort_values(by=['Wins'], ascending=True)
                if not nemesis_df.empty:
                    nem = nemesis_df.iloc[0]
                    st.error(f"⚠️ **Nemesis:** {nem['Opponent']} ({nem['Win Rate']} Win Rate)")
                else: st.caption("No Nemesis found yet.")

            st.divider()
            st.subheader("🤝 Synergy Radar")
            if syn_df is not None and not syn_df.empty:
                duo_df = syn_df[syn_df['Total Games'] >= 2].sort_values(by=['Net MMR Impact'], ascending=False)
                if not duo_df.empty:
                    duo = duo_df.iloc[0]
                    st.success(f"🤝 **Dynamic Duo:** {duo['Teammate']} ({duo['Win Rate']} Win Rate)")

        with col_p2:
            st.subheader("📊 Deep Analytics")
            if st.button(f"Generate Teammate Matrix for {hero}", width='stretch'):
                if syn_df is not None: st.dataframe(syn_df, width='stretch', hide_index=True)
            if st.button(f"Analyze {hero}'s Fatigue Curve", width='stretch'):
                s_df = engine.get_stamina_analysis(display_logs, hero)
                if s_df is not None: st.dataframe(s_df, width='stretch', hide_index=True)
            
            st.divider()
            st.subheader("⚔️ Direct Head-to-Head")
            rival = st.selectbox("Compare vs specific Rival:", player_list)
            if st.button("Analyze Direct H2H", width='stretch'):
                h2h = engine.get_h2h(display_logs, hero, rival)
                if h2h and h2h["matches"]:
                    st.write(f"### {hero} {h2h['p1_wins']} - {h2h['p2_wins']} {rival}")
                    st.table(pd.DataFrame(h2h["matches"]))

        st.divider()
        st.subheader("📜 Career Ledger & Rank History")
        hist_df = engine.get_player_history(display_logs, hero)
        
        if hist_df is not None and not hist_df.empty:
            chart_data = hist_df.iloc[::-1].reset_index(drop=True)
            st.line_chart(chart_data['Balance'], use_container_width=True)
            st.dataframe(hist_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No history found.")

    # --- TAB 3: FAQ ---
    with tab3:
        st.subheader("📖 FAQ & Game Manual")
        
        with st.expander("🎭 Archetypes Legend", expanded=True):
            st.write("""
            Your **Archetype** is determined by your career stats and playstyle:
            - **🎖️ The General:** Legend rank or higher who consistently elevates their partners.
            - **🧪 The Catalyst:** High 'Force Multiplier' (APD). You make every teammate better.
            - **🛡️ The Tank:** High 'Opponent Difficulty' (AOD). You face the toughest matchups.
            - **⚔️ Giant Slayer:** Multiple underdog wins against players 300+ MMR higher than you.
            - **🔥 The Finisher:** Master of momentum with high session win streaks (4+).
            - **🦾 Iron Man:** High stamina and volume (30% more games than league average).
            - **🎯 The Specialist:** High efficiency winner with a 58%+ win rate.
            - **🐣 New Challenger:** Players still in the Rookie calibration phase.
            - **🏸 Consistent Force:** The reliable backbone of the community.
            """)

        with st.expander("⚔️ How does the Underdog (Giant Slayer) Bonus work?"):
            st.write("""
            If you beat a team where at least one opponent has **300+ MMR more than you**, you get a **Giant Slayer bonus**:
            - You receive an injection of up to **+80 MMR** on top of your base win points.
            - These wins are tracked in your Hall of Fame as **'Giants Slayed'**.
            - Note: In v1.4.2, the MMR ceiling was removed, so all Tiers can now earn this bonus!
            """)

        with st.expander("🛡️ What is a Rookie Shield?"):
            st.write(f"New friends are protected for their first **{config.ROOKIE_SHIELD_GAMES} games**. You gain full MMR for wins, but lose only -10 MMR on losses.")

        with st.expander("💠 What are the Tiers?"):
            st.table(pd.DataFrame([
                {"Tier": "Master", "MMR Range": "1000-1499"}, {"Tier": "Grandmaster", "MMR Range": "1500-1899"},
                {"Tier": "Epic", "MMR Range": "1900-2299"}, {"Tier": "Legend", "MMR Range": "2300-2699"},
                {"Tier": "Mythic", "MMR Range": "2700-3199"}, {"Tier": "Mythic Glory", "MMR Range": "3200+"}
            ]))
        
        st.divider()
        st.info("💡 **Note:** v5.4.3 Archetypes use calibrated thresholds for the current league meta.")

else:
    st.warning("⚠️ Waiting for Registry Sync...")

st.divider()
st.caption("v5.4.3 | Fadu & Friends Community Rankings | Manila 2026")