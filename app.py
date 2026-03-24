import streamlit as st
import requests
import pandas as pd
import config # Ensure we import config to access the master list
from engine import FaduMMREngine
from auditor import ai_audit_session

# --- 1. DASHBOARD CONFIGURATION ---
# Wide layout is essential for the 13-column Fadu standard leaderboard.
st.set_page_config(
    page_title="Fadu MMR Power Rankings v1.2.9",
    page_icon="🏸",
    layout="wide"
)

# --- 2. SIDEBAR STATUS & TOGGLES ---
with st.sidebar:
    st.title("🏸 Fadu Ops")
    
    # Connection Indicators (preserving registry/auditor health checks)
    if "BRIDGE_URL" in st.secrets:
        st.success("Registry Connection: 🟢 Online")
    else:
        st.error("Registry Connection: 🔴 Offline")
        
    # DIRECT REGISTRY LINK
    # Direct shortcut to the master data source as per Fadu Ops Manual.
    st.markdown("### 📊 Data Source")
    st.markdown("[🔗 Open Official Google Registry](https://docs.google.com/spreadsheets/d/1mPd-WUmyrwC5MEtBbADzyTmJJpOqr7MZPueloFUYyHo/edit?usp=sharing)")
    
    st.divider()
        
    if "GROQ_API_KEY" in st.secrets:
        st.success("AI Auditor: 🟢 Online")
    else:
        st.error("AI Auditor: 🔴 Offline")
        
    st.divider()
    
    # CONTROL PANEL: Global calculation settings
    st.subheader("⚙️ Control Panel")
    sync_enabled = st.checkbox(
        "Enable Cloud Sync", 
        value=True, 
        help="If unchecked, calculations stay local and won't overwrite Google Sheets."
    )
    
    st.divider()

    # UPDATED: VIEW FILTERS (Synced to Config Rookie Threshold)
    st.subheader("🎯 View Filters")
    hide_inactive = st.checkbox(
        "Hide Inactive", 
        value=False, 
        help="Removes players who have missed 4 or more consecutive sessions."
    )
    hide_rookies = st.checkbox(
        f"Hide Rookies (< {config.ROOKIE_SHIELD_GAMES} games)", 
        value=False, 
        help=f"Removes players with less than {config.ROOKIE_SHIELD_GAMES} total games played."
    )
    show_present_only = st.checkbox(
        "Show present on last session only",
        value=False,
        help="Filters the list to show only players who appeared in the most recent log date."
    )

    # DYNAMIC HIDDEN COUNT WARNING
    if 'lb' in st.session_state:
        df_full = st.session_state.lb
        
        # Check for presence of all required filter columns in the dataframe
        required_cols = ['Missed_Sessions', 'Total_Games', 'Is_Present']
        if all(col in df_full.columns for col in required_cols):
            df_temp = df_full.copy()
            if hide_inactive:
                df_temp = df_temp[df_temp['Missed_Sessions'] < 4]
            if hide_rookies:
                df_temp = df_temp[df_temp['Total_Games'] >= config.ROOKIE_SHIELD_GAMES]
            if show_present_only:
                df_temp = df_temp[df_temp['Is_Present'] == True]
            
            hidden_count = len(df_full) - len(df_temp)
            if hidden_count > 0:
                st.warning(f"🚫 Players Hidden: {hidden_count}")
            else:
                st.info("✅ Showing Full Roster")
        else:
            st.error("⚠️ Filter Error: Engine/App Mismatch. Please re-run Calculate.")
    
    st.divider()

    # LEAGUE SEEDS REFERENCE
    with st.expander("💠 Initial Seeded Roster"):
        st.caption("The following players began the season with a veteran seed of 1500 MMR:")
        seed_string = ", ".join(config.SEEDS)
        st.write(f"**{seed_string}**")
    
    st.divider()
    
    # Versioning and Metadata
    st.caption("v1.2.9 | Elite Analytics Build")
    st.info("🔥 **Decay Alert:** MMR Decay (-50) triggers after 3 missed sessions.")
    st.info("📍 Quezon City, PH")

# --- 3. MAIN UI INPUT ---
st.title("🏸 Fadu Badminton Power Rankings")
st.markdown("Automated MMR processing with Stamina Fatigue Analysis and Force Multiplier tracking.")

input_area = st.text_area(
    "Match Logs Input:", 
    height=300, 
    placeholder="Paste your chronological logs here...",
    help="Ensure the date format matches your engine parser (e.g., 22-Mar)."
)

# Layout for action buttons
c1, c2, _ = st.columns([1.5, 1.5, 4])

# --- 4. ACTION: AUDIT ---
with c1:
    # 2026 FIX: Replaced use_container_width with width='stretch'
    if st.button("🔍 Run Session Audit", width='stretch'):
        if 'audit_report' in st.session_state: 
            del st.session_state['audit_report']
            
        if not input_area.strip():
            st.warning("Please paste logs first.")
        else:
            with st.spinner("Phonetic & Duplicate Check..."):
                engine = FaduMMREngine()
                _, _, _, _ = engine.simulate(input_area) 
                
                report = ai_audit_session(input_area, list(engine.players.keys()))
                st.session_state.audit_report = report

# Audit Findings Display
if 'audit_report' in st.session_state:
    st.info(f"### 📋 Audit Findings\n{st.session_state.audit_report}")
    if st.button("Close Audit Report"):
        del st.session_state.audit_report
        st.rerun()

# --- 5. ACTION: CALCULATE & SYNC ---
with c2:
    # 2026 FIX: Replaced use_container_width with width='stretch'
    if st.button("🚀 Calculate & Sync", type="primary", width='stretch'):
        if not input_area.strip():
            st.warning("Please paste logs first.")
        else:
            with st.spinner("Processing MMR Math..."):
                engine = FaduMMREngine()
                
                # Unpack the 4-tuple from the engine (Table, Date, Drift, DecayList)
                df, last_date, drift, decayed = engine.simulate(input_area)
                
                # Persist results in session state
                st.session_state.lb = df
                st.session_state.drift = drift
                st.session_state.date = last_date
                st.session_state.decayed = decayed 
                
                # Handle Cloud Sync logic based on Safety Toggle
                if sync_enabled:
                    if "BRIDGE_URL" in st.secrets:
                        payload = {"target": "Registry", "headers": df.columns.tolist(), "values": df.values.tolist()}
                        try:
                            resp = requests.post(st.secrets["BRIDGE_URL"], json=payload, timeout=20)
                            if resp.status_code == 200:
                                st.success(f"🎉 Registry Updated: {resp.text}")
                            else:
                                st.error(f"❌ Sync Error: {resp.status_code}")
                                st.write(resp.text)
                        except Exception as e:
                            st.error(f"❌ Connection Failed: {str(e)}")
                    else:
                        st.error("Missing BRIDGE_URL in secrets.")
                else:
                    st.info("💡 Sync Disabled: Calculations are local only.")

# --- 6. RESULTS AND ANALYSIS TABS ---
if 'lb' in st.session_state:
    st.divider()
    
    # --- HEATMAP DECAY NOTIFICATION ---
    if st.session_state.get('decayed'):
        with st.expander("📉 Inactivity Decay Alert (Heatmap)", expanded=True):
            st.warning(f"The following players suffered MMR Decay on {st.session_state.date} due to 3+ missed sessions.")
            
            decay_df = pd.DataFrame(st.session_state.decayed)
            
            def style_decay_heatmap(val):
                color = '#e67e22' if val <= 4 else '#c0392b'
                return f'background-color: {color}; color: white; font-weight: bold'

            # 2026 FIX: map() replaces applymap(); width='stretch' replaces use_container_width
            st.dataframe(
                decay_df.style.map(style_decay_heatmap, subset=['Missed']),
                width='stretch',
                hide_index=True
            )

    # Tab navigation
    tab1, tab2 = st.tabs(["🏆 Leaderboard", "⚔️ Combat & Synergy"])

    # --- TAB 1: LEADERBOARD ---
    with tab1:
        st.metric("Session Wealth Drift", f"{st.session_state.drift} MMR")
        st.subheader(f"📅 Results for: {st.session_state.date}")
        
        # Search Filter (UI-side)
        search = st.text_input("🔍 Search Player:", placeholder="Filter by name...", key="p_search")
        
        # APPLY UI FILTERS TO THE DATAFRAME
        display_df = st.session_state.lb.copy()
        
        if search:
            display_df = display_df[display_df['Player'].str.contains(search, case=False)]
        
        if hide_inactive and 'Missed_Sessions' in display_df.columns:
            display_df = display_df[display_df['Missed_Sessions'] < 4]
            
        if hide_rookies and 'Total_Games' in display_df.columns:
            display_df = display_df[display_df['Total_Games'] >= config.ROOKIE_SHIELD_GAMES]
            
        if show_present_only and 'Is_Present' in display_df.columns:
            display_df = display_df[display_df['Is_Present'] == True]
        
        # CLEANUP: Remove internal tracking columns before displaying to user
        final_cols = [c for c in display_df.columns if c not in ["Total_Games", "Missed_Sessions", "Is_Present"]]
        
        # 2026 FIX: width='stretch'
        st.dataframe(display_df[final_cols], width='stretch', hide_index=True)

    # --- TAB 2: COMBAT & SYNERGY ---
    with tab2:
        player_list = sorted(st.session_state.lb['Player'].tolist())
        st.subheader("👤 Select Profile to Analyze")
        hero = st.selectbox("Choose Player:", player_list, key="p1_select")
        
        st.divider()
        col_m1, col_m2 = st.columns(2)
        
        # PART A: SYNERGY & STAMINA
        with col_m1:
            # 1. STAMINA PHASE ANALYSIS
            st.subheader("🔋 Stamina Phase Analysis")
            st.caption(f"Does {hero}'s performance drop as the session progresses?")
            if st.button(f"Analyze Stamina for {hero}", width='stretch'):
                engine = FaduMMREngine()
                stamina_df = engine.get_stamina_analysis(input_area, hero)
                if stamina_df is not None:
                    st.dataframe(stamina_df, width='stretch', hide_index=True)
                else:
                    st.warning("Not enough game sequence data found.")

            st.divider()

            # 2. TEAMMATE SYNERGY (With Force Multiplier)
            st.subheader("🤝 Teammate Synergy & Impact")
            st.caption(f"Win rates and the Net MMR wealth {hero} generated for partners.")
            if st.button(f"Generate Synergy Matrix for {hero}", width='stretch'):
                engine = FaduMMREngine()
                synergy_df = engine.get_teammate_matrix(input_area, hero)
                if synergy_df is not None:
                    st.dataframe(synergy_df, width='stretch', hide_index=True)
                else:
                    st.warning("No partner games found.")
        
        # PART B: RIVALRIES
        with col_m2:
            # 1. OPPONENT MATRIX
            st.subheader("📊 Opponent Matrix")
            st.caption(f"Historical win/loss record against specific rivals.")
            if st.button(f"Generate Career Matrix for {hero}", width='stretch'):
                engine = FaduMMREngine()
                rival_df = engine.get_rivalry_matrix(input_area, hero)
                if rival_df is not None:
                    st.dataframe(rival_df, width='stretch', hide_index=True)
                else:
                    st.warning("No opponent data found.")
            
            st.divider()

            # 2. DIRECT H2H
            st.subheader("⚔️ Head-to-Head Lookup")
            rival = st.selectbox("Compare against specific Rival:", player_list, key="p2_select")
                
            if st.button("Analyze Direct H2H", width='stretch'):
                engine = FaduMMREngine()
                h2h = engine.get_h2h(input_area, hero, rival)
                
                if h2h and h2h["matches"]:
                    st.write(f"### {hero} {h2h['p1_wins']} - {h2h['p2_wins']} {rival}")
                    st.table(pd.DataFrame(h2h["matches"]))
                else:
                    st.warning("No direct matches found.")

# --- 7. FOOTER ---
st.divider()
st.caption("v1.2.9 | Fadu Badminton Elite Analytics Build | Manila Build")