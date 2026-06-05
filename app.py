# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import numpy as np
import re
import urllib.parse
import plotly.express as px 
import plotly.graph_objects as go
import config # Ensure we import config to access the master list
from engine import FaduMMREngine
from auditor import ai_audit_session

# --- 1. DASHBOARD CONFIGURATION ---
# Milestone: v6.2.9 - Scoreboard & Robust Parser Update
st.set_page_config(
    page_title="Fadu & Friends Portal v6.2.9",
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
        for col in ["APD", "AOD", "MMR", "Peak", "+/-", "Total_Games", "Underdog Wins", "Trend", "Initial MMR", "Rookie_Trend"]:
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

@st.cache_data(ttl=600)
def get_cached_duos_leaderboard(raw_logs):
    """Calculates pair stats once and caches the result for tab-switching performance."""
    if not raw_logs or not str(raw_logs).strip():
        return None
    
    engine = FaduMMREngine()
    return engine.get_pairs_leaderboard(raw_logs)

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
    st.caption("v6.2.9 | Frontier Momentum")
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
                    st.session_state.parse_errors = engine.parse_errors

    with c2:
        if st.button("🚀 Calculate & Sync", type="primary", width='stretch'):
            if not input_area.strip(): st.warning("Please paste logs first.")
            else:
                with st.spinner("Syncing Major Update..."):
                    engine = FaduMMREngine()
                    df, last_date, drift, decayed, errors, games_df = engine.simulate(input_area)
                    st.session_state.lb, st.session_state.drift = df, drift
                    st.session_state.date, st.session_state.decayed = last_date, decayed 
                    st.session_state.parse_errors = errors
                    st.session_state.admin_logs = input_area
                    
                    if sync_enabled and "BRIDGE_URL" in st.secrets:
                        payload_lb = {"target": "Registry", "headers": df.columns.tolist(), "values": df.values.tolist()}
                        log_lines = [[line] for line in input_area.split('\n')]
                        payload_hist = {"target": "Match_History", "headers": ["Raw_Logs"], "values": log_lines}
                        payload_games = {"target": "Games_Log", "headers": games_df.columns.tolist(), "values": games_df.values.tolist()}
                        
                        try:
                            requests.post(st.secrets["BRIDGE_URL"], json=payload_lb, timeout=20)
                            requests.post(st.secrets["BRIDGE_URL"], json=payload_hist, timeout=20)
                            requests.post(st.secrets["BRIDGE_URL"], json=payload_games, timeout=20)
                            st.success("🎉 Global Registry & History Updated!")
                            st.cache_data.clear()
                        except:
                            st.error("Sync Failed")

    if 'audit_report' in st.session_state:
        st.info(f"### 📋 Audit Findings\n{st.session_state.audit_report}")
        if st.button("Close Audit"): del st.session_state.audit_report; st.rerun()

    if 'parse_errors' in st.session_state and st.session_state.parse_errors:
        with st.expander("🚨 Parser Warnings (Skipped Logs)", expanded=True):
            st.write("Cross-reference the line numbers below with your input to fix formatting.")
            for err in st.session_state.parse_errors:
                st.error(f"**Line {err['line']}**: {err['msg']}  \n`{err['raw']}`")
            
            st.divider()
            st.caption("Reference View (Copy/Paste corrected lines from here):")
            st.code(input_area, line_numbers=True)

            if st.button("🗑️ Clear Warnings"):
                st.session_state.parse_errors = []
                st.rerun()

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
        all_dates = re.findall(r'^(\d{1,2}-[A-Za-z]+)', display_logs, re.MULTILINE)
        session_date = all_dates[-1] if all_dates else "Latest Session"
    else:
        session_date = "Cloud Sync"

if display_lb is not None:
    # --- ROBUST COLUMN INITIALIZATION ---
    # Ensures public sheet data matches engine expectations to prevent KeyErrors
    required_metrics = [
        "Rank", "Player", "Archetype", "Tier", "MMR", "Peak", "Max Streak", 
        "Underdog Wins", "+/-", "AOD", "APD", "Status", "Confidence", 
        "Last Session", "Season Record", "Remarks", "Total_Games", 
        "Missed_Sessions", "Is_Present", "Initial MMR", "Trend", "Rookie_Trend"
    ]
    for col in required_metrics:
        if col not in display_lb.columns:
            if col == "Archetype": display_lb[col] = "Consistent Force"
            elif col == "Remarks": display_lb[col] = "Active Competitor"
            elif col == "Is_Present": display_lb[col] = False
            else: display_lb[col] = 0

    tab1, tab2, tab3 = st.tabs(["📊 RANKINGS", "⚔️ COMBAT & SYNERGY", "📖 FAQ"])

    # --- TAB 1: RANKINGS ---
    with tab1:
        st.markdown(f"###### 🌟 Last Session Highlights ({session_date})")
        present_df = display_lb[display_lb['Is_Present'] == True] if 'Is_Present' in display_lb.columns else pd.DataFrame()
        
        m_col1, m_col2 = st.columns(2)
        m_col3, m_col4 = st.columns(2)
        
        if not present_df.empty:
            if '+/-' in present_df.columns:
                mvp_row = present_df.loc[present_df['+/-'].idxmax()]
                m_col1.metric("🔥 Session MVP", mvp_row['Player'], f"+{int(mvp_row['+/-'])}", 
                             help="Highest MMR gain in the latest session. The dominant force of the day.")
                
            if 'APD' in present_df.columns:
                carry_row = present_df.loc[present_df['APD'].idxmin()]
                m_col2.metric("🏋️ Session Carry", carry_row['Player'], f"{int(carry_row['APD'])} APD", 
                             help="The player who overcame the toughest Partner Impact (APD), lifting their teammates to victory.")

            if 'AOD' in present_df.columns:
                tank_row = present_df.loc[present_df['AOD'].idxmax()]
                m_col3.metric("🛡️ Session Tank", tank_row['Player'], f"{int(tank_row['AOD'])} AOD", 
                             help="The player who faced the highest Opponent Difficulty (AOD) today. The frontline of the session.")
            
            if 'MMR' in present_df.columns:
                m_col4.metric("📉 Session Intensity", f"{int(present_df['MMR'].mean())}", "Avg MMR", 
                             help="The average MMR of all players present today. A measure of the session's overall skill ceiling.")
        else:
            st.caption("No active session data available for highlights.")

        st.divider()

        st.markdown("###### 👑 Season Leaders (All-Time)")
        h_col1, h_col2, h_col3 = st.columns(3)
        h_col4, h_col5, h_col6 = st.columns(3)

        leader = display_lb.iloc[0]
        h_col1.metric("🏆 League Leader", leader['Player'], f"Rank #1 ({leader['Tier']})", 
                     help="The current highest-rated player in the community.")

        if 'Total_Games' in display_lb.columns:
            ironman_row = display_lb.loc[display_lb['Total_Games'].idxmax()]
            h_col2.metric("🦾 Iron Man", ironman_row['Player'], f"{int(ironman_row['Total_Games'])} G", 
                         help="The player with the highest total game volume this season. Pure dedication.")

        # Find player with highest trend, ensuring they have at least 1 MMR gain to avoid tie-defaults
        potential_improved = display_lb[display_lb['Trend'] > 0]
        # Ensure display_logs is treated as a string and handle flexible date detection
        log_text = str(display_logs) if display_logs else ""
        session_count = len(re.findall(r'^(\d{1,2}-[A-Za-z]+)', log_text, re.MULTILINE))

        if not potential_improved.empty and session_count > 1:
            # Tie-break: if trends are equal, the higher ranked player (MMR) wins the highlight
            improved_row = potential_improved.sort_values(by=["Trend", "MMR"], ascending=False).iloc[0]
            h_col3.metric("📈 Most Improved", f"{improved_row['Player']} 🚀", f"+{int(round(improved_row['Trend']))} MMR",
                         help="The largest MMR gain over the last 5 weeks (approx. 1 month). This rewards recent performance rather than starting point.")
        else:
            h_col3.metric("📈 Most Improved", "N/A", "0 MMR", help="No significant climb detected in the last 5 weeks.")
        if 'Underdog Wins' in display_lb.columns:
            slayer_row = display_lb.loc[display_lb['Underdog Wins'].idxmax()]
            h_col4.metric("⚔️ Giant Slayer", slayer_row['Player'], f"{int(slayer_row['Underdog Wins'])} Slays", 
                         help="The master of upsets. Most wins against opponents rated 300+ points higher.")

        potential_rookies = display_lb[display_lb['Rookie_Trend'] > 0]
        if not potential_rookies.empty:
            rookie_row = potential_rookies.sort_values(by=["Rookie_Trend", "MMR"], ascending=False).iloc[0]
            h_col5.metric("🐣 Rookie of the Month", f"{rookie_row['Player']} ✨", f"+{int(rookie_row['Rookie_Trend'])} MMR",
                         help="The best performing player among those who debuted within the last 5 weeks.")
        else:
            h_col5.metric("🐣 Rookie of the Month", "N/A", "0 MMR", help="No new debuts with positive growth detected.")

        h_col6.metric("📉 Session Intensity", f"{int(present_df['MMR'].mean()) if not present_df.empty else 0}", "Avg MMR", 
                     help="The current skill ceiling of the latest session.")


        st.divider()
        search = st.text_input("🔍 Search Player:", placeholder="Filter by name...", key="p_search")
        df_disp = display_lb.copy()
        if search: df_disp = df_disp[df_disp['Player'].str.contains(search, case=False)]
        
        if hide_inactive: df_disp = df_disp[df_disp['Missed_Sessions'] < 4]
        if hide_rookies: df_disp = df_disp[df_disp['Total_Games'] >= config.ROOKIE_SHIELD_GAMES]
        if show_present_only: df_disp = df_disp[df_disp['Is_Present'] == True]
        
        original_13 = ["Rank", "Player", "Tier", "MMR", "Peak", "+/-", "AOD", "APD", "Status", "Confidence", "Last Session", "Season Record", "Remarks"]
        final_cols = [c for c in original_13 if c in df_disp.columns]
        st.dataframe(df_disp[final_cols], width='stretch', hide_index=True)

        st.divider()
        st.subheader("👥 THE DYNAMIC DUOS LEADERBOARD")
        
        duo_config = {
            "Rank": st.column_config.NumberColumn("Rank", help="Team standing based on Combined MMR."),
            "Pair / Duo": st.column_config.TextColumn("Pair / Duo", help="The two players in this partnership."),
            "Combined MMR": st.column_config.NumberColumn("Combined MMR", help="The average skill rating (Power Level) of the duo. Used for primary ranking."),
            "Win %": st.column_config.TextColumn("Win %", help="Actual win rate of this specific duo over at least 3 games."),
            "Synergy Delta": st.column_config.TextColumn("Synergy Delta", help="Performance vs. Expectation. (+) means you play better together than apart. (-) means styles may clash."),
            "Archetype": st.column_config.TextColumn("Archetype", help="Classification based on team strength and chemistry.")
        }

        with st.spinner("Analyzing Team Synergy..."):
            duos_df = get_cached_duos_leaderboard(display_logs)
            if duos_df is not None:
                st.dataframe(duos_df, use_container_width=True, hide_index=True, column_config=duo_config)
            else:
                st.info("Insufficient data for Duo analysis. Pairs must play at least 3 games together.")

    # --- TAB 2: COMBAT & SYNERGY ---
    with tab2:
        st.subheader("👥 THE DYNAMIC DUOS LEADERBOARD")
        with st.spinner("Analyzing Team Synergy..."):
            duos_df = get_cached_duos_leaderboard(display_logs)
            if duos_df is not None:
                st.dataframe(duos_df, use_container_width=True, hide_index=True, column_config=duo_config)
            else:
                st.info("Insufficient data for Duo analysis. Pairs must play at least 3 games together.")
        st.divider()

        player_list = sorted([p.strip() for p in display_lb['Player'].tolist()])
        
        # --- DEEP LINKING LOGIC ---
        query_params = st.query_params
        default_ix = 0
        if "player" in query_params and query_params["player"] in player_list:
            default_ix = player_list.index(query_params["player"])
        
        hero = st.selectbox("Select Player Profile:", player_list, index=default_ix)
        if hero:
            st.query_params["player"] = hero
            
        st.divider()
        
        engine = FaduMMREngine()
        hero_row = display_lb.loc[display_lb['Player'].str.strip() == hero]
        
        if not hero_row.empty:
            st.subheader(f"{hero_row['Archetype'].values[0]} : {hero}", anchor=False)
            
            # COPY-LINK UI
            safe_hero = urllib.parse.quote(hero)
            profile_url = f"https://faduscommunityrankings.streamlit.app/?player={safe_hero}"
            st.caption("📋 Share this Profile (Click icon to copy):")
            st.code(profile_url, language=None)

            st.markdown("#### 🏛️ Hall of Fame")
            
            # --- HARDENED WIN RATE LOGIC ---
            rec_str = str(hero_row['Season Record'].values[0])
            nums = re.findall(r'(\d+)', rec_str)
            w_val = int(nums[0]) if len(nums) > 0 else 0
            l_val = int(nums[1]) if len(nums) > 1 else 0
            total_g = w_val + l_val
            wr = (w_val / total_g * 100) if total_g > 0 else 0
            
            # DESKTOP REPAIR: 3 Columns Top / 2 Columns Bottom
            row1_1, row1_2, row1_3 = st.columns(3)
            row2_1, row2_2 = st.columns(2)
            
            row1_1.metric("🏆 Peak MMR", f"{int(hero_row['Peak'].values[0])}", help="Highest rating ever achieved.")
            row1_2.metric("🔥 Max Streak", f"{int(hero_row['Max Streak'].values[0])}", help="Most wins in a single session.")
            row1_3.metric("⚔️ Underdog Wins", f"{int(hero_row['Underdog Wins'].values[0])}", help="Wins vs opponents 300+ higher MMR.")
            
            row2_1.metric("📊 Career Win Rate", f"{wr:.1f}%", f"{w_val}W - {l_val}L", delta_color="normal" if wr >= 50 else "inverse")
            row2_2.metric("🏟️ Total Volume", f"{int(hero_row['Total_Games'].values[0])} Games", help="Total ranked matches played.")

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

            c_a, c_b = st.columns(2)
            with c_a:
                if st.button(f"Generate Teammate Matrix for {hero}", width='stretch'):
                    if syn_df is not None: st.dataframe(syn_df, width='stretch', hide_index=True)
            with c_b:
                if st.button(f"Generate Rivalry Matrix for {hero}", width='stretch'):
                    if riv_df is not None: st.dataframe(riv_df, width='stretch', hide_index=True)
            
            st.divider()
            rival = st.selectbox("Compare vs Rival:", player_list)
            if st.button("Analyze Direct H2H", width='stretch'):
                h2h = engine.get_h2h(display_logs, hero, rival)
                if h2h and h2h["matches"]:
                    # --- NEW: BOLD SCOREBOARD ---
                    st.write(f"### {hero} vs {rival}")
                    st.markdown(f"## {hero} {h2h['p1_wins']} \u2014 {h2h['p2_wins']} {rival}")
                    
                    # --- FRONTIER MOMENTUM: STEPPED AREA LOGIC ---
                    matches = h2h["matches"]
                    x_history = [0]
                    y_history = [0]
                    current_lead = 0
                    
                    for i, match in enumerate(matches, 1):
                        # Identify winner and determine lead direction
                        point = 1 if hero in match['Winner'] else -1
                        
                        # First point: Stay at current lead, move to current game start (Vertical rise)
                        x_history.append(current_lead)
                        y_history.append(i)
                        
                        # Second point: Step to new lead at current game end (Horizontal move)
                        current_lead += point
                        x_history.append(current_lead)
                        y_history.append(i)

                    fig = go.Figure()

                    # Hero Territory (Positive Lead)
                    fig.add_trace(go.Scatter(
                        x=[max(0, x) for x in x_history],
                        y=y_history,
                        mode='lines',
                        line_shape='vh',
                        fill='tozerox',
                        fillcolor='rgba(0, 255, 136, 0.7)',
                        line=dict(color='#00ff88', width=3),
                        name=f"{hero} Momentum"
                    ))

                    # Rival Territory (Negative Lead)
                    fig.add_trace(go.Scatter(
                        x=[min(0, x) for x in x_history],
                        y=y_history,
                        mode='lines',
                        line_shape='vh',
                        fill='tozerox',
                        fillcolor='rgba(255, 75, 75, 0.7)',
                        line=dict(color='#ff4b4b', width=3),
                        name=f"{rival} Momentum"
                    ))
                    
                    limit = max([abs(x) for x in x_history]) + 1
                    fig.update_layout(
                        template='plotly_dark',
                        xaxis=dict(
                            title=f"Net Lead (← {rival} | {hero} →)", 
                            range=[-limit, limit], 
                            showgrid=False,
                            showticklabels=True,
                            zeroline=False
                        ),
                        yaxis=dict(
                            title="Game Number", 
                            autorange="reversed", 
                            showgrid=False,
                            showticklabels=True
                        ),
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        height=500,
                        showlegend=False
                    )
                    fig.add_vline(x=0, line_color="white", line_width=3)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Style Matchup Cards (Side-by-side comparison)
                    rival_row = display_lb.loc[display_lb['Player'].str.strip() == rival]
                    if not rival_row.empty:
                        col_h, col_r = st.columns(2)
                        with col_h:
                            st.info(f"**{hero} Style**\nAOD: {hero_row['AOD'].values[0]}\nAPD: {hero_row['APD'].values[0]}")
                        with col_r:
                            st.warning(f"**{rival} Style**\nAOD: {rival_row['AOD'].values[0]}\nAPD: {rival_row['APD'].values[0]}")
                    
                    raw_m_df = pd.DataFrame(h2h["matches"])
        
                    # Safely display available columns
                    display_cols = [c for c in ['Date', 'Winner', 'Loser', 'Score'] if c in raw_m_df.columns]
                    st.table(raw_m_df[display_cols])

        st.divider()
        with st.expander("📜 Career Ledger & History", expanded=False):


        st.divider()
        with st.expander("📜 Career Ledger & History", expanded=False):
            if st.button(f"Analyze {hero}'s Fatigue Curve", width='stretch'):
                s_df = engine.get_stamina_analysis(display_logs, hero)
                if s_df is not None: st.dataframe(s_df, width='stretch', hide_index=True)
                
            hist_df = engine.get_player_history(display_logs, hero)
            if hist_df is not None and not hist_df.empty:
                # Chronological assignment for Game X numbering
                hist_disp = hist_df.iloc[::-1].copy() 
                hist_disp.insert(0, "No.", [f"Game {i+1}" for i in range(len(hist_disp))])
                
                # Descending view for display (Latest games at the top)
                hist_final = hist_disp.iloc[::-1]
                
                # --- Plotly Progression Chart with Tier Thresholds ---
                chart_data = hist_disp.reset_index(drop=True)
                fig_hist = go.Figure()
                
                # Main MMR Progress Line
                fig_hist.add_trace(go.Scatter(
                    x=chart_data.index + 1,
                    y=chart_data['Balance'],
                    mode='lines+markers',
                    name='MMR',
                    line=dict(color='#00ff88', width=3),
                    marker=dict(size=6, color='#00ff88'),
                    hovertemplate='<b>Game %{x}</b><br>MMR: %{y}<br>Result: %{customdata}<extra></extra>',
                    customdata=chart_data['Result']
                ))
                
                # Add Horizontal Tier Thresholds
                for tier_name, threshold in config.TIER_THRESHOLDS:
                    if threshold > 0:
                        fig_hist.add_hline(
                            y=threshold, 
                            line_dash="dash", 
                            line_color="rgba(255, 255, 255, 0.2)",
                            annotation_text=f" {tier_name}",
                            annotation_position="top left",
                            annotation_font_size=10,
                            annotation_font_color="rgba(255, 255, 255, 0.4)"
                        )

                fig_hist.update_layout(
                    template='plotly_dark',
                    height=400,
                    margin=dict(l=20, r=20, t=40, b=20),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(title="Matches Played (Chronological)", showgrid=False),
                    yaxis=dict(title="MMR Rating", showgrid=True, gridcolor='rgba(255,255,255,0.05)'),
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig_hist, use_container_width=True)
                st.dataframe(hist_final, use_container_width=True, hide_index=True)

    # --- TAB 3: FAQ & PHILOSOPHY ---
    with tab3:
        st.subheader("📖 FAQ & Game Manual")
        
        if st.button("📜 View Version History", width='stretch'):
            show_version_history()
        
        with st.expander("🏸 Why are we tracking MMR?", expanded=True):
            st.markdown("""
            **It’s not about who is better; it’s about making sure every session feels like a Finals match.**
            
            The math helps us build groups where everyone gets to play at their limit, ensuring no one is bored and no one is overwhelmed. 
            The MMR system is simply the compass we use to find that balance. 
            """)

        with st.expander("📊 What is APD (Average Partner Delta)?"):
            st.markdown(r"""
            **APD stands for Average Partner Delta.** In 2v2 badminton, this is your **"Carrying Metric"**. 
            It calculates the average MMR difference between you and the partner sharing your side of the court.

            **While AOD looks at who you are fighting, APD looks at who is helping you.**

            **Why does it matter? (The Badminton Example)**
            *   **Player X** has a high win rate, but their APD is **Positive (+200)**. This means they are almost always paired up with veterans ranked 200 points higher than them. They are being supported.
            *   **Player Y** has a similar win rate, but their APD is **Negative (-200)**. This means they are constantly paired with partners ranked 200 points lower than them.

            Without APD, it looks like they are equal. With APD, the group can see that Player Y is a **"Master Carrier"**—they are winning matches while elevating and dragging lower-ranked partners across the finish line.

            **How it works in a Match:**
            When you step onto the court, the engine calculates the "Gap" between you and your partner:
            $$\text{Match Delta} = \text{Partner's MMR} - \text{Your MMR}$$
            
            *   **Negative APD** = You are the higher-rated player in the duo. You are the **Anchor**.
            *   **Positive APD** = You are the lower-rated player in the duo. You are **Supported**.
            """)

        with st.expander("⚔️ What is AOD (Average Opponent Difficulty)?"):
            st.markdown(r"""
            **AOD stands for Average Opponent Difficulty.** Think of it as your **"Strength of Schedule"**. 
            It calculates the average MMR (matchmaking rating) of all the opponents you have stepped on the court against.

            **While your win rate only shows if you won, AOD shows how hard the fight was.**

            **Why does it matter? (The Badminton Example)**
            *   **Player A** has an 80% win rate, but they mostly play against rookies or lower-ranked players. Their AOD is **Low**.
            *   **Player B** has a 50% win rate, but they are constantly sharing the court with your group's top-tier, "Mythic"-level players. Their AOD is **High**.

            Without AOD, the leaderboard makes Player A look dominant. With AOD, the group can see that Player B is actually surviving the ultimate gauntlet, making their 50% win rate incredibly impressive.

            **How it works in a Match:**
            When you enter a 2v2 match, the engine looks at the average MMR of the two players on the opposing side:
            $$\text{Opponent Team Average MMR} = \frac{\text{Opponent 1 MMR} + \text{Opponent 2 MMR}}{2}$$
            That number gets added to your running career average. If you constantly face stacked teams, your AOD climbs. If your opponent difficulty is higher than your own ranking, it even triggers the Underdog Bonuses!
            """)

        with st.expander("� What are Rust Mechanics (Inactivity Decay)?"):
            st.markdown("""
            **To keep the rankings active and accurate, we use a "Rust" system (Inactivity Decay).**
            
            * **The Rule:** If you miss **4 or more consecutive sessions**, your MMR begins to decay.
            * **The Logic:** Skill fades with inactivity. Decay ensures they don't hold an artificially high rank while inactive.
            """)

        with st.expander("📊 Data Analysis & The 'Layer of Fun'"):
            st.markdown("""
            We believe that badminton is as much a mental game as it is a physical one. By introducing deep-dive analytics—like 
            **Stamina Curves**, **Dynamic Duos**, and **Rivalry Radars**—we are adding a "Manager Mode" layer to our sessions. 
            """)

        with st.expander("🎭 Archetypes Legend"):
            st.write("""
            Your **Archetype** is determined by your career stats and playstyle:
            - **🎖️ The General:** Legend rank or higher who consistently elevates their partners.
            - **🧪 The Catalyst:** High 'Force Multiplier' (APD). You make every teammate better.
            - **💎 The Supported:** High win rate while consistently paired with higher-rated veterans.
            - **🛡️ The Tank:** High 'Opponent Difficulty' (AOD). You face the toughest matchups.
            - **⚔️ Giant Slayer:** Multiple underdog wins against players 300+ MMR higher than you.
            - **🔥 The Finisher:** Master of momentum with high session win streaks (4+).
            - **🦾 Iron Man:** High stamina and volume (30% more games than league average).
            - **🎯 The Specialist:** High efficiency winner with a 58%+ win rate.
            - **🐣 New Challenger:** Players still in the Rookie calibration phase.
            - **🏸 Consistent Force:** The reliable backbone of the community.
            """)

        with st.expander("👯 How does the Dynamic Duos Leaderboard work?"):
            st.markdown(r"""
            **The Duos Leaderboard tracks the performance of specific 2v2 partnerships.**
            
            *   **The Entry Requirement:** A pair must play at least **3 games together** to appear on the leaderboard.
            *   **Combined MMR:** This is the average skill rating of the partnership. It represents the collective "Power Level" of a team. 
                $$\text{Combined MMR} = \frac{\text{Player 1 MMR} + \text{Player 2 MMR}}{2}$$
                The leaderboard is primarily sorted by this metric to identify the league's top-tier teams.
            *   **Synergy Delta:** This is the most important metric. It compares the pair's actual win rate against the average win rate of the two individuals when they play with other people.
                *   **Positive Delta (+):** You play better together than you do apart.
                *   **Negative Delta (-):** Your styles might be clashing.
            *   **Duo Archetypes:**
                *   💖 **The Power Couple:** Synergy Delta > 10%. A match made in heaven.
                *   🚀 **The Unstoppables:** Win rate of 70% or higher.
                *   🗼 **Twin Towers:** Both players are high-tier (Combined MMR 2300+).
                *   🚫 **Oil and Water:** Synergy Delta < -10%. Great players, but a tough fit together.
                *   ⚖️ **Balanced Duo:** Consistent performance relative to individual skill.
            """)

        with st.expander("⚔️ How does the Underdog (Giant Slayer) Bonus work?"):
            st.write("""
            If you beat a team where at least one opponent has **300+ MMR more than you**, you get a **Giant Slayer bonus**:
            - You receive an injection of up to **+80 MMR** on top of your base win points.
            - These wins are tracked in your Hall of Fame as **'Giants Slayed'**.
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
        st.info("💡 **Note:** v6.2.9 Calibration: Inactivity Decay (Rust) is active for players missing 4+ sessions.")

else:
    st.warning("⚠️ Waiting for Registry Sync...")

# --- ADMIN OPERATIONAL OVERSIGHT (BOTTOM) ---
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
st.caption("v6.2.9 | Fadu & Friends Community Rankings | Manila 2026")