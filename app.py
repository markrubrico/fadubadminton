import streamlit as st
import requests
import pandas as pd
import numpy as np
import config # Ensure we import config to access the master list
from engine import FaduMMREngine
from auditor import ai_audit_session

# --- 1. DASHBOARD CONFIGURATION ---
# Milestone: v6.1.0 - The Elite Oversight Update (Validated Highlights & Season Cards)
st.set_page_config(
    page_title="Fadu & Friends Portal v6.1.0",
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
        
        # TYPE-SAFETY: Force 'Player' to string to prevent 'ug' disappearing.
        lb_df = pd.read_csv(reg_url)
        lb_df['Player'] = lb_df['Player'].astype(str)
        
        # Convert numeric columns safely, coercing errors (like date strings) to NaN
        for col in ["APD", "AOD", "MMR", "Peak", "+/-", "Total_Games", "Underdog Wins"]:
            if col in lb_df.columns:
                lb_df[col] = pd.to_numeric(lb_df[col], errors='coerce').fillna(0)
        
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
    st.subheader("🎯 View Filters")
    hide_inactive = st.checkbox("Hide Inactive", value=False, help="Removes players with 4+ missed sessions.")
    hide_rookies = st.checkbox(f"Hide Rookies (< {config.ROOKIE_SHIELD_GAMES} games)", value=False)
    show_present_only = st.checkbox("Show last session only", value=False)

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
    st.caption("v6.1.0 | Elite Oversight")
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

# DYNAMIC DATE DETECTION
if is_admin and 'lb' in st.session_state:
    display_lb, display_logs = st.session_state.lb, st.session_state.get('admin_logs', "")
    session_date = st.session_state.get('date', "Latest")
else:
    display_lb, display_logs = public_lb, public_logs
    if display_logs:
        import re
        all_dates = re.findall(r'^(\d{1,2}-[A-Za-z]+)', display_logs, re.MULTILINE)
        session_date = all_dates[-1] if all_dates else "Latest Session"
    else:
        session_date = "Cloud Sync"

if display_lb is not None:
    # Consistency check for required highlight columns
    for col in ["Max Streak", "Underdog Wins", "Archetype", "Total_Games"]:
        if col not in display_lb.columns:
            display_lb[col] = 0 if col != "Archetype" else "Consistent Force"

    tab1, tab2, tab3 = st.tabs(["📊 RANKINGS", "⚔️ COMBAT & SYNERGY", "📖 FAQ"])

    # --- TAB 1: RANKINGS (MOBILE OPTIMIZED) ---
    with tab1:
        # --- SESSION HIGHLIGHTS (STRICT PRESENCE VALIDATION) ---
        st.markdown(f"###### 🌟 Last Session Highlights ({session_date})")
        
        # Filter strictly for players present in the last session to avoid ghost MVPs
        present_df = display_lb[display_lb['Is_Present'] == True] if 'Is_Present' in display_lb.columns else pd.DataFrame()
        
        m_col1, m_col2 = st.columns(2)
        m_col3, m_col4 = st.columns(2)
        
        if not present_df.empty:
            if '+/-' in present_df.columns:
                mvp_row = present_df.loc[present_df['+/-'].idxmax()]
                m_col1.metric("🔥 Session MVP", mvp_row['Player'], f"+{int(mvp_row['+/-'])}", help="Highest gain today.")
                
            if 'APD' in present_df.columns:
                carry_row = present_df.loc[present_df['APD'].idxmin()]
                m_col2.metric("🏋️ Session Carry", carry_row['Player'], f"{int(carry_row['APD'])} APD", help="Most weight lifted today.")

            if 'AOD' in present_df.columns:
                tank_row = present_df.loc[present_df['AOD'].idxmax()]
                m_col3.metric("🛡️ Session Tank", tank_row['Player'], f"{int(tank_row['AOD'])} AOD", help="Toughest schedule today.")
            
            if 'MMR' in present_df.columns:
                m_col4.metric("📉 Session Intensity", f"{int(present_df['MMR'].mean())}", "Avg MMR")
        else:
            st.caption("No active session data available for highlights.")

        st.divider()

        # --- SEASON HIGHLIGHTS (LEAGUE-WIDE HALL OF FAME) ---
        st.markdown("###### 👑 Season Leaders (All-Time)")
        h_col1, h_col2 = st.columns(2)
        h_col3, h_col4 = st.columns(2)

        # 1. League Leader
        leader = display_lb.iloc[0]
        h_col1.metric("🏆 League Leader", leader['Player'], f"Rank #1 ({leader['Tier']})")

        # 2. Iron Man (Volume)
        if 'Total_Games' in display_lb.columns:
            ironman_row = display_lb.loc[display_lb['Total_Games'].idxmax()]
            h_col2.metric("🦾 Iron Man", ironman_row['Player'], f"{int(ironman_row['Total_Games'])} Games", help="Most games played this season.")

        # 3. Most Improved (Current MMR vs Peak Min)
        # Using Peak as a proxy for 'Best' while MMR represents 'Current Growth'
        improved_row = display_lb.loc[(display_lb['MMR'] - display_lb['Peak'].min()).idxmax()]
        h_col3.metric("📈 Most Improved", improved_row['Player'], f"{int(improved_row['MMR'])} MMR", help="Highest climb from floor.")

        # 4. Giant Slayer (Underdog Wins)
        if 'Underdog Wins' in display_lb.columns:
            slayer_row = display_lb.loc[display_lb['Underdog Wins'].idxmax()]
            h_col4.metric("⚔️ Giant Slayer", slayer_row['Player'], f"{int(slayer_row['Underdog Wins'])} Slays", help="Most underdog victories.")

        st.divider()
        search = st.text_input("🔍 Search Player:", placeholder="Filter by name...", key="p_search")
        df_disp = display_lb.copy()
        if search: df_disp = df_disp[df_disp['Player'].str.contains(search, case=False)]
        
        if hide_inactive and 'Missed_Sessions' in df_disp.columns: df_disp = df_disp[df_disp['Missed_Sessions'] < 4]
        if hide_rookies and 'Total_Games' in df_disp.columns: df_disp = df_disp[df_disp['Total_Games'] >= config.ROOKIE_SHIELD_GAMES]
        if show_present_only and 'Is_Present' in df_disp.columns: df_disp = df_disp[df_disp['Is_Present'] == True]
        
        original_13 = ["Rank", "Player", "Tier", "MMR", "Peak", "+/-", "AOD", "APD", "Status", "Confidence", "Last Session", "Season Record", "Remarks"]
        final_cols = [c for c in original_13 if c in df_disp.columns]
        
        st.dataframe(
            df_disp[final_cols], 
            width='stretch', 
            hide_index=True,
            column_config={
                "AOD": st.column_config.NumberColumn("AOD", help="Opponent Difficulty."),
                "APD": st.column_config.NumberColumn("APD", help="Partner Impact."),
                "Confidence": st.column_config.TextColumn("Conf", help="Reliability."),
                "Remarks": st.column_config.TextColumn("Remarks", width="large")
            }
        )

    # --- TAB 2: COMBAT & SYNERGY ---
    with tab2:
        player_list = sorted([p.strip() for p in display_lb['Player'].tolist()])
        hero = st.selectbox("Select Player Profile:", player_list)
        st.divider()
        
        engine = FaduMMREngine()
        hero_row = display_lb.loc[display_lb['Player'].str.strip() == hero]
        
        if not hero_row.empty:
            st.markdown(f"## {hero_row['Archetype'].values[0]} : {hero}")
            st.markdown("#### 🏛️ Hall of Fame")
            f1, f2 = st.columns(2)
            f3, f4 = st.columns(2)
            f1.metric("🏆 Peak", f"{int(hero_row['Peak'].values[0])}")
            f2.metric("🔥 Streak", f"{int(hero_row['Max Streak'].values[0])}")
            f3.metric("⚔️ Slayed", f"{int(hero_row['Underdog Wins'].values[0])}")
            f4.metric("📈 Record", hero_row['Season Record'].values[0])

        st.divider()
        with st.container():
            st.subheader("🛡️ Road to Mythic")
            if not hero_row.empty:
                current_mmr = hero_row['MMR'].values[0]
                st.write(f"**Rank:** {hero_row['Tier'].values[0]} ({int(current_mmr)})")
                st.progress(min(max((current_mmr - 1000) / 2200, 0.0), 1.0))
        
        st.divider()
        with st.expander("📊 Synergy & Rivalry Analytics"):
            riv_df = engine.get_rivalry_matrix(display_logs, hero)
            syn_df = engine.get_teammate_matrix(display_logs, hero)
            
            if riv_df is not None and not riv_df.empty:
                nemesis_df = riv_df[riv_df['Total'] >= 2].sort_values(by=['Wins'], ascending=True)
                if not nemesis_df.empty:
                    st.error(f"⚠️ **Nemesis:** {nemesis_df.iloc[0]['Opponent']} ({nemesis_df.iloc[0]['Win Rate']} WR)")

            if syn_df is not None and not syn_df.empty:
                duo_df = syn_df[syn_df['Total Games'] >= 2].sort_values(by=['Net MMR Impact'], ascending=False)
                if not duo_df.empty:
                    st.success(f"🤝 **Dynamic Duo:** {duo_df.iloc[0]['Teammate']} ({duo_df.iloc[0]['Win Rate']} WR)")

            if st.button(f"Generate Teammate Matrix for {hero}", width='stretch'):
                if syn_df is not None: st.dataframe(syn_df, width='stretch', hide_index=True)
            
            rival = st.selectbox("Compare vs Rival:", player_list)
            if st.button("Analyze Direct H2H", width='stretch'):
                h2h = engine.get_h2h(display_logs, hero, rival)
                if h2h and h2h["matches"]:
                    st.write(f"### {hero} {h2h['p1_wins']} - {h2h['p2_wins']} {rival}")
                    st.table(pd.DataFrame(h2h["matches"]))

        st.divider()
        with st.expander("📜 Career Ledger & History", expanded=False):
            if st.button(f"Analyze {hero}'s Fatigue Curve", width='stretch'):
                s_df = engine.get_stamina_analysis(display_logs, hero)
                if s_df is not None: st.dataframe(s_df, width='stretch', hide_index=True)
                
            hist_df = engine.get_player_history(display_logs, hero)
            if hist_df is not None and not hist_df.empty:
                st.line_chart(hist_df.iloc[::-1].reset_index(drop=True)['Balance'], use_container_width=True)
                st.dataframe(hist_df, use_container_width=True, hide_index=True)

    # --- TAB 3: FAQ ---
    with tab3:
        st.subheader("📖 FAQ & Game Manual")
        
        with st.expander("🏸 Why are we tracking MMR?", expanded=True):
            st.markdown("""
            **It’s not about who is better; it’s about making sure every session feels like a Finals match.**
            
            The math helps us build groups where everyone gets to play at their limit, ensuring no one is bored and no one is overwhelmed. 
            The heart of our community lies in those "21-19" games—the ones where every serve matters and every rally is earned. 
            The MMR system is simply the compass we use to find that balance. 
            """)

        with st.expander("📊 Data Analysis & The 'Layer of Fun'"):
            st.markdown("""
            We believe that badminton is as much a mental game as it is a physical one. By introducing deep-dive analytics—like 
            **Stamina Curves**, **Dynamic Duos**, and **Rivalry Radars**—we are adding a "Manager Mode" layer to our sessions. 
            """)

        with st.expander("🎭 Archetypes Legend"):
            st.write("""
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

        with st.expander("🛡️ What is a Rookie Shield?"):
            st.write(f"New friends are protected for their first **{config.ROOKIE_SHIELD_GAMES} games**. You gain full MMR for wins, but lose only -10 MMR on losses.")

        with st.expander("💠 What are the Tiers?"):
            st.table(pd.DataFrame([
                {"Tier": "Master", "MMR Range": "1000-1499"}, {"Tier": "Grandmaster", "MMR Range": "1500-1899"},
                {"Tier": "Epic", "MMR Range": "1900-2299"}, {"Tier": "Legend", "MMR Range": "2300-2699"},
                {"Tier": "Mythic", "MMR Range": "2700-3199"}, {"Tier": "Mythic Glory", "MMR Range": "3200+"}
            ]))

else:
    st.warning("⚠️ Waiting for Registry Sync...")

# --- ADMIN VIEW: REPOSITIONED RUST REPORT & DRIFT (BOTTOM) ---
if is_admin:
    st.divider()
    st.subheader("📊 Operational Oversight")
    
    if 'decayed' in st.session_state:
        with st.expander("📉 Inactivity Decay Report (Rust Log)", expanded=False):
            if st.session_state.decayed:
                decay_df = pd.DataFrame(st.session_state.decayed)
                st.warning(f"Total Wealth Drift (Inactivity Penalty): {decay_df['Penalty'].sum()}")
                st.table(decay_df)
            else:
                st.success("No players currently in rust decay.")
    
    if 'drift' in st.session_state:
        st.caption(f"Session Wealth Drift: {st.session_state.drift} MMR")

st.divider()
st.caption("v6.1.0 | Fadu & Friends Community Rankings | Manila 2026")