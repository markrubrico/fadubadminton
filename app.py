import streamlit as st
import requests
import pandas as pd
from engine import FaduMMREngine
from auditor import ai_audit_session

# --- 1. DASHBOARD CONFIGURATION ---
# We maintain the wide layout and official league title branding.
st.set_page_config(
    page_title="Fadu MMR Power Rankings v1.1.8",
    page_icon="🏸",
    layout="wide"
)

# --- 2. SIDEBAR STATUS & TOGGLES ---
with st.sidebar:
    st.title("🏸 Fadu Ops")
    
    # Connection Indicators (preserving v1.1.7 registry/auditor checks)
    if "BRIDGE_URL" in st.secrets:
        st.success("Registry Connection: 🟢 Online")
    else:
        st.error("Registry Connection: 🔴 Offline")
        
    if "GROQ_API_KEY" in st.secrets:
        st.success("AI Auditor: 🟢 Online")
    else:
        st.error("AI Auditor: 🔴 Offline")
        
    st.divider()
    
    # CONTROL PANEL (The Safety Toggle logic)
    st.subheader("⚙️ Control Panel")
    sync_enabled = st.checkbox(
        "Enable Cloud Sync", 
        value=True, 
        help="If unchecked, calculations stay local and won't overwrite Google Sheets."
    )
    
    st.divider()
    
    # Versioning and Metadata
    st.caption("v1.1.8 | Heatmap Awareness Build")
    st.info("🔥 **Decay Alert:** MMR Decay (-50) triggers after 3 missed sessions.")
    st.info("📍 Quezon City, PH | 1:50 AM")

# --- 3. MAIN UI INPUT ---
st.title("🏸 Fadu Badminton Power Rankings")
st.markdown("Automated MMR processing with Inactivity Decay tracking and Rivalry analysis.")

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
    if st.button("🔍 Run Session Audit", use_container_width=True):
        if 'audit_report' in st.session_state: 
            del st.session_state['audit_report']
            
        if not input_area.strip():
            st.warning("Please paste logs first.")
        else:
            with st.spinner("Phonetic & Duplicate Check..."):
                engine = FaduMMREngine()
                # Unpack all 4 values to match the v1.1.7 engine signature
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
            with st.spinner("Processing MMR Math..."):
                engine = FaduMMREngine()
                
                # Unpack the 4-tuple from the engine
                df, last_date, drift, decayed = engine.simulate(input_area)
                
                # Persist results in session state
                st.session_state.lb = df
                st.session_state.drift = drift
                st.session_state.date = last_date
                st.session_state.decayed = decayed # List of dicts: {Player, Penalty, Missed}
                
                # Handle Cloud Sync logic
                if sync_enabled:
                    if "BRIDGE_URL" in st.secrets:
                        payload = {"target": "Registry", "headers": df.columns.tolist(), "values": df.values.tolist()}
                        try:
                            resp = requests.post(st.secrets["BRIDGE_URL"], json=payload, timeout=20)
                            if resp.status_code == 200:
                                st.success(f"🎉 Registry Updated: {resp.text}")
                            else:
                                st.error(f"❌ Sync Error: {resp.status_code}")
                        except Exception as e:
                            st.error(f"❌ Connection Failed: {str(e)}")
                else:
                    st.info("💡 Sync Disabled: Calculations are local only.")

# --- 6. RESULTS AND ANALYSIS TABS ---
if 'lb' in st.session_state:
    st.divider()
    
    # --- HEATMAP DECAY NOTIFICATION ---
    if st.session_state.get('decayed'):
        with st.expander("📉 Inactivity Decay Alert (Heatmap)", expanded=True):
            st.warning(f"The following players suffered MMR Decay on {st.session_state.date} due to 3+ missed sessions.")
            
            # Convert list to DataFrame for styling
            decay_df = pd.DataFrame(st.session_state.decayed)
            
            # Function to apply heat coloring to the 'Missed' column
            def style_decay_heatmap(val):
                # 4 sessions = Light Orange, 5+ = Deep Red
                if val <= 4: color = '#e67e22' 
                else: color = '#c0392b'
                return f'background-color: {color}; color: white; font-weight: bold'

            # Apply the style and display
            st.dataframe(
                decay_df.style.applymap(style_decay_heatmap, subset=['Missed']),
                use_container_width=True,
                hide_index=True
            )

    # Tab navigation
    tab1, tab2 = st.tabs(["🏆 Leaderboard", "⚔️ Rivalries & Matrix"])

    with tab1:
        st.metric("Session Wealth Drift", f"{st.session_state.drift} MMR")
        st.subheader(f"📅 Results for: {st.session_state.date}")
        
        # Search Filter
        search = st.text_input("🔍 Search Player:", placeholder="Filter by name...", key="p_search")
        df_disp = st.session_state.lb
        if search:
            df_disp = df_disp[df_disp['Player'].str.contains(search, case=False)]
        
        st.dataframe(df_disp, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("⚔️ Rivalry Lookup")
        player_list = sorted(st.session_state.lb['Player'].tolist())
        h1, h2 = st.columns(2)
        
        with h1:
            hero = st.selectbox("Select Hero Player:", player_list, key="p1_select")
        with h2:
            rival = st.selectbox("Select Rival Player:", player_list, key="p2_select")
            
        if st.button("Analyze Direct H2H", use_container_width=True):
            engine = FaduMMREngine()
            h2h = engine.get_h2h(input_area, hero, rival)
            
            if h2h and h2h["matches"]:
                st.divider()
                st.write(f"### {hero} {h2h['p1_wins']} - {h2h['p2_wins']} {rival}")
                st.table(pd.DataFrame(h2h["matches"]))
            else:
                st.warning("No direct matches found.")
        
        st.divider()
        
        # Action: Career Matrix
        st.subheader(f"📊 {hero}'s Opponent Matrix")
        if st.button(f"Generate Career Matrix for {hero}", use_container_width=True):
            engine = FaduMMREngine()
            matrix_df = engine.get_rivalry_matrix(input_area, hero)
            if matrix_df is not None:
                st.dataframe(matrix_df, use_container_width=True, hide_index=True)

# --- 7. FOOTER ---
st.divider()
st.caption("v1.1.8 | Fadu Badminton Power Ranking System | Manila Build")