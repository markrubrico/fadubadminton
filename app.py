import streamlit as st
import requests
import pandas as pd
from engine import FaduMMREngine
from auditor import ai_audit_session

# --- 1. DASHBOARD CONFIGURATION ---
# We keep the wide layout and specific naming convention for the league.
st.set_page_config(
    page_title="Fadu MMR Power Rankings v1.1.7",
    page_icon="🏸",
    layout="wide"
)

# --- 2. SIDEBAR STATUS & TOGGLES ---
with st.sidebar:
    st.title("🏸 Fadu Ops")
    
    # Connection Indicators (preserved from v1.1.6)
    if "BRIDGE_URL" in st.secrets:
        st.success("Registry Connection: 🟢 Online")
    else:
        st.error("Registry Connection: 🔴 Offline")
        
    if "GROQ_API_KEY" in st.secrets:
        st.success("AI Auditor: 🟢 Online")
    else:
        st.error("AI Auditor: 🔴 Offline")
        
    st.divider()
    
    # CONTROL PANEL (The Safety Toggle from v1.1.6)
    st.subheader("⚙️ Control Panel")
    sync_enabled = st.checkbox(
        "Enable Cloud Sync", 
        value=True, 
        help="If unchecked, calculations stay local and won't overwrite Google Sheets."
    )
    
    st.divider()
    
    # Versioning and Metadata
    st.caption("v1.1.7 | Decay Awareness & Matrix Build")
    st.info("💡 **Decay Alert:** MMR Decay (-50) triggers after 3 missed sessions.")
    st.info("📍 Location: Quezon City, PH")

# --- 3. MAIN UI INPUT ---
st.title("🏸 Fadu Badminton Power Rankings")
st.markdown("Calculate session standings, analyze rivalries, and audit match logs.")

input_area = st.text_area(
    "Match Logs Input:", 
    height=300, 
    placeholder="Paste your chronological logs here (e.g., 20-Feb | Game 1: W: Name...)",
    help="Ensure the date format follows 'DD-Month' (e.g., 22-Mar)."
)

# Layout for action buttons
c1, c2, _ = st.columns([1.5, 1.5, 4])

# --- 4. ACTION: AUDIT ---
with c1:
    if st.button("🔍 Run Session Audit", use_container_width=True):
        if 'audit_report' in st.session_state: 
            del st.session_state['audit_report']
            
        if not input_area.strip():
            st.warning("Please paste logs first.")
        else:
            with st.spinner("Phonetic & Duplicate Check..."):
                engine = FaduMMREngine()
                # Run once locally to initialize the player roster for the auditor
                # We unpack all 4 values to match the v1.1.7 engine signature
                _, _, _, _ = engine.simulate(input_area) 
                
                # Run the AI audit logic
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
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not input_area.strip():
            st.warning("Please paste logs first.")
        else:
            with st.spinner("Processing MMR Math & Cloud Handshake..."):
                engine = FaduMMREngine()
                
                # V1.1.7 UPDATE: The engine now returns 4 values (the 4th is the Decay List)
                df, last_date, drift, decayed = engine.simulate(input_area)
                
                # Persist results in session state for the UI
                st.session_state.lb = df
                st.session_state.drift = drift
                st.session_state.date = last_date
                st.session_state.decayed = decayed # Tracked for the alert box
                
                # Logic check for the Safety Toggle (from v1.1.6)
                if sync_enabled:
                    if "BRIDGE_URL" in st.secrets:
                        payload = {
                            "target": "Registry", 
                            "headers": df.columns.tolist(), 
                            "values": df.values.tolist()
                        }
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
    
    # --- NEW FEATURE: DECAY ALERT BOX ---
    # We display this warning only if players actually decayed in the final session.
    if st.session_state.get('decayed'):
        with st.expander("📉 Inactivity Decay Alert", expanded=True):
            st.warning(f"The following players suffered MMR Decay on {st.session_state.date} due to inactivity (3+ missed sessions):")
            st.table(pd.DataFrame(st.session_state.decayed))

    # Tab navigation for a clean UI
    tab1, tab2 = st.tabs(["🏆 Leaderboard", "⚔️ Rivalries & Matrix"])

    # LEADERBOARD TAB
    with tab1:
        st.metric("Session Wealth Drift", f"{st.session_state.drift} MMR")
        st.subheader(f"📅 Results for: {st.session_state.date}")
        
        # Player Search Filter
        search = st.text_input("🔍 Search Player:", placeholder="Type a name...", key="p_search")
        df_disp = st.session_state.lb
        if search:
            df_disp = df_disp[df_disp['Player'].str.contains(search, case=False)]
        
        st.dataframe(df_disp, use_container_width=True, hide_index=True)

    # RIVALRY TAB
    with tab2:
        st.subheader("⚔️ Rivalry Lookup")
        st.write("Analyze face-to-face matchups and career dominance.")
        
        # Build the player list from the current rankings
        player_list = sorted(st.session_state.lb['Player'].tolist())
        h1, h2 = st.columns(2)
        
        with h1:
            hero = st.selectbox("Select Hero Player:", player_list, key="p1_select")
        with h2:
            rival = st.selectbox("Select Rival Player:", player_list, key="p2_select")
            
        # Action: Direct H2H Breakdown
        if st.button("Analyze Direct H2H", use_container_width=True):
            engine = FaduMMREngine()
            h2h = engine.get_h2h(input_area, hero, rival)
            
            if h2h and h2h["matches"]:
                st.divider()
                st.write(f"### {hero} {h2h['p1_wins']} - {h2h['p2_wins']} {rival}")
                st.table(pd.DataFrame(h2h["matches"]))
            else:
                st.warning(f"No direct matches found between {hero} and {rival}.")
        
        st.divider()
        
        # Action: Full Career Matrix
        st.subheader(f"📊 {hero}'s Opponent Matrix")
        st.caption("A summary of performance against every unique opponent.")
        
        if st.button(f"Generate Career Matrix for {hero}", use_container_width=True):
            engine = FaduMMREngine()
            matrix_df = engine.get_rivalry_matrix(input_area, hero)
            
            if matrix_df is not None:
                st.dataframe(matrix_df, use_container_width=True, hide_index=True)
            else:
                st.warning(f"No opponent data found for {hero} in the logs.")

# --- 7. FOOTER ---
st.divider()
st.caption("v1.1.7 | Fadu Badminton Power Ranking System | Modular Baseline")