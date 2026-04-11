import streamlit as st
import requests
import pandas as pd
import config # Master list & threshold configs
from engine import FaduMMREngine
from auditor import ai_audit_session

# --- 1. DASHBOARD CONFIGURATION ---
st.set_page_config(
    page_title="Fadu MMR Portal v4.6.0",
    page_icon="🏸",
    layout="wide"
)

# --- 2. DATA BRIDGE: PUBLIC FETCHING (The "Player" Source) ---
@st.cache_data(ttl=600)  # Data refreshes every 10 minutes for players
def fetch_public_data():
    """Pulls current Registry and Match_History from Published Google Sheet CSVs."""
    reg_url = st.secrets.get("REGISTRY_CSV_URL", "")
    hist_url = st.secrets.get("HISTORY_CSV_URL", "")
    
    try:
        if not reg_url or not hist_url:
            return None, None
        
        lb_df = pd.read_csv(reg_url)
        hist_df = pd.read_csv(hist_url)
        
        # Reconstruct multi-line string from the Match_History sheet for the analytics engine
        raw_history = "\n".join(hist_df.iloc[:, 0].astype(str).tolist())
        return lb_df, raw_history
    except Exception:
        return None, None

# --- 3. SIDEBAR: THE CONDITIONAL GATEKEEPER ---
with st.sidebar:
    st.title("🏸 Fadu Ops")
    
    # 🔐 ACCESS CONTROL
    # This is the "Conditional View" trigger.
    ops_key = st.text_input("Admin Access Key", type="password", help="Enter key to unlock Admin Console.")
    is_admin = (ops_key == st.secrets.get("OPS_PASSWORD", "fadu2026"))
    
    if is_admin:
        st.success("👨‍⚖️ Admin Mode: Authorized")
        sync_enabled = st.checkbox("Enable Cloud Sync", value=True)
    else:
        st.info("👋 Player Mode: Read-Only")

    st.divider()

    # Connection Status
    if "BRIDGE_URL" in st.secrets:
        st.success("Registry Connection: 🟢 Online")
    else:
        st.error("Registry Connection: 🔴 Offline")
        
    st.markdown("### 📊 Data Source")
    st.markdown("[🔗 Open Google Registry](https://docs.google.com/spreadsheets/d/1mPd-WUmyrwC5MEtBbADzyTmJJpOqr7MZPueloFUYyHo/edit?usp=sharing)")
    
    st.divider()
        
    if "GROQ_API_KEY" in st.secrets:
        st.success("AI Auditor: 🟢 Online")
    else:
        st.error("AI Auditor: 🔴 Offline")
    
    st.divider()

    # VIEW FILTERS
    st.subheader("🎯 View Filters")
    hide_inactive = st.checkbox("Hide Inactive (4+ Misses)", value=False)
    hide_rookies = st.checkbox(f"Hide Rookies (< {config.ROOKIE_SHIELD_GAMES} games)", value=False)
    show_present_only = st.checkbox("Show last session only", value=False)

    # Filter Logic for Hidden Count Warning
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
    st.caption("v4.6.0 | Unified Portal Build")
    st.info("🔥 MMR Decay triggers after 3 missed sessions.")

# --- 4. DATA LOADING ---
public_lb, public_logs = fetch_public_data()

# --- 5. ADMIN VIEW: COMMISSIONER CONSOLE (CONDITIONAL) ---
if is_admin:
    st.title("🛠️ Commissioner Console")
    st.markdown("Recalculate the entire ecosystem and sync to the cloud.")

    input_area = st.text_area(
        "Match Logs Input (Full History):", 
        height=300, 
        placeholder="Paste chronological logs here...",
        value=st.session_state.get('last_input', "")
    )

    c1, c2, _ = st.columns([1.5, 1.5, 4])

    with c1:
        if st.button("🔍 Run Session Audit", width='stretch'):
            if not input_area.strip(): st.warning("Please paste logs.")
            else:
                with st.spinner("Auditing..."):
                    engine = FaduMMREngine()
                    engine.simulate(input_area) 
                    report = ai_audit_session(input_area, list(engine.players.keys()))
                    st.session_state.audit_report = report

    with c2:
        if st.button("🚀 Calculate & Sync", type="primary", width='stretch'):
            if not input_area.strip(): st.warning("Please paste logs.")
            else:
                with st.spinner("Processing & Syncing..."):
                    engine = FaduMMREngine()
                    df, last_date, drift, decayed = engine.simulate(input_area)
                    
                    st.session_state.lb = df
                    st.session_state.drift = drift
                    st.session_state.date = last_date
                    st.session_state.decayed = decayed 
                    st.session_state.admin_logs = input_area
                    
                    if sync_enabled and "BRIDGE_URL" in st.secrets:
                        payload_lb = {"target": "Registry", "headers": df.columns.tolist(), "values": df.values.tolist()}
                        log_lines = [[line] for line in input_area.split('\n')]
                        payload_hist = {"target": "Match_History", "headers": ["Raw_Logs"], "values": log_lines}
                        
                        try:
                            requests.post(st.secrets["BRIDGE_URL"], json=payload_lb, timeout=20)
                            requests.post(st.secrets["BRIDGE_URL"], json=payload_hist, timeout=20)
                            st.success("🎉 Registry & History Updated!")
                            st.cache_data.clear()
                        except:
                            st.error("Sync Failed")

    if 'audit_report' in st.session_state:
        st.info(f"### 📋 Audit Findings\n{st.session_state.audit_report}")
        if st.button("Close Audit"): del st.session_state.audit_report; st.rerun()

# --- 6. PLAYER VIEW & ANALYTICS ---
st.divider()
st.title("🏆 Fadu Badminton Power Rankings")

# Determine data source: Admin Session vs Public Registry
if is_admin and 'lb' in st.session_state:
    display_lb = st.session_state.lb
    display_logs = st.session_state.get('admin_logs', "")
else:
    display_lb = public_lb
    display_logs = public_logs

if display_lb is not None:
    # Heatmap logic for admin session
    if is_admin and st.session_state.get('decayed'):
        with st.expander("📉 Inactivity Decay Alert", expanded=True):
            decay_df = pd.DataFrame(st.session_state.decayed)
            st.dataframe(decay_df.style.map(lambda v: 'background-color: #c0392b; color: white' if v > 4 else 'background-color: #e67e22; color: white', subset=['Missed']), width='stretch', hide_index=True)

    tab1, tab2 = st.tabs(["🏆 Leaderboard", "⚔️ Combat & Synergy"])

    with tab1:
        if is_admin: st.metric("Session Wealth Drift", f"{st.session_state.drift} MMR")
        search = st.text_input("🔍 Search Player:", placeholder="Name filter...")
        
        df_disp = display_lb.copy()
        if search: df_disp = df_disp[df_disp['Player'].str.contains(search, case=False)]
        if hide_inactive: df_disp = df_disp[df_disp['Missed_Sessions'] < 4]
        if hide_rookies: df_disp = df_disp[df_disp['Total_Games'] >= config.ROOKIE_SHIELD_GAMES]
        if show_present_only: df_disp = df_disp[df_disp['Is_Present'] == True]
        
        cols = [c for c in df_disp.columns if c not in ["Total_Games", "Missed_Sessions", "Is_Present"]]
        st.dataframe(df_disp[cols], width='stretch', hide_index=True)

    with tab2:
        player_list = sorted(display_lb['Player'].tolist())
        hero = st.selectbox("Choose Player:", player_list)
        st.divider()
        c_m1, c_m2 = st.columns(2)
        engine = FaduMMREngine()
        
        with c_m1:
            st.subheader("🔋 Stamina Phase")
            if st.button(f"Analyze Stamina for {hero}", width='stretch'):
                s_df = engine.get_stamina_analysis(display_logs, hero)
                if s_df is not None: st.dataframe(s_df, width='stretch', hide_index=True)
            
            st.divider()
            st.subheader("🤝 Synergy")
            if st.button(f"Generate Synergy Matrix for {hero}", width='stretch'):
                syn_df = engine.get_teammate_matrix(display_logs, hero)
                if syn_df is not None: st.dataframe(syn_df, width='stretch', hide_index=True)
        
        with c_m2:
            st.subheader("📊 Opponent Matrix")
            if st.button(f"Generate Career Matrix for {hero}", width='stretch'):
                riv_df = engine.get_rivalry_matrix(display_logs, hero)
                if riv_df is not None: st.dataframe(riv_df, width='stretch', hide_index=True)
            
            st.divider()
            st.subheader("⚔️ Head-to-Head")
            rival = st.selectbox("Compare against Rival:", player_list)
            if st.button("Analyze Direct H2H", width='stretch'):
                h2h = engine.get_h2h(display_logs, hero, rival)
                if h2h and h2h["matches"]:
                    st.write(f"### {hero} {h2h['p1_wins']} - {h2h['p2_wins']} {rival}")
                    st.table(pd.DataFrame(h2h["matches"]))
else:
    st.warning("⚠️ Waiting for Registry Sync...")

st.divider()
st.caption("v4.6.0 | Manila 2026")