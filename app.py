import streamlit as st
import requests
import pandas as pd
from engine import FaduMMREngine
from auditor import ai_audit_session

# --- DASHBOARD CONFIG ---
st.set_page_config(page_title="Fadu MMR v1.1.2", layout="wide")

# --- SIDEBAR STATUS ---
with st.sidebar:
    st.title("🏸 Fadu Ops")
    if "BRIDGE_URL" in st.secrets:
        st.success("Registry: 🟢 Online")
    else:
        st.error("Registry: 🔴 Offline")
        
    if "GROQ_API_KEY" in st.secrets:
        st.success("Auditor: 🟢 Online")
    else:
        st.error("Auditor: 🔴 Offline")
        
    st.divider()
    st.caption("v1.1.2 | Rivalry & Matrix Build")
    st.info("Tip: Head over to the Rivalry tab after calculating to see careers and direct matchups.")

# --- MAIN UI ---
st.title("🏸 Fadu Badminton Power Rankings")
input_area = st.text_area("Match Logs Input:", height=300, placeholder="Paste your chronological logs here...")

c1, c2, _ = st.columns([1.5, 1.5, 4])

# --- ACTION: AUDIT ---
with c1:
    if st.button("🔍 Run Session Audit", use_container_width=True):
        if 'audit_report' in st.session_state: del st.session_state['audit_report']
        if not input_area.strip():
            st.warning("Please paste logs first.")
        else:
            with st.spinner("Phonetic & Duplicate Check..."):
                engine = FaduMMREngine()
                # Initialize engine roster for auditor context
                _, _, _ = engine.simulate(input_area) 
                st.session_state.audit_report = ai_audit_session(input_area, list(engine.players.keys()))

if 'audit_report' in st.session_state:
    st.info(f"### 📋 Audit Findings\n{st.session_state.audit_report}")
    if st.button("Close Audit"):
        del st.session_state.audit_report
        st.rerun()

# --- ACTION: CALCULATE & SYNC ---
with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not input_area.strip():
            st.warning("Please paste logs first.")
        else:
            with st.spinner("Syncing to Cloud Registry..."):
                engine = FaduMMREngine()
                df, last_date, drift = engine.simulate(input_area)
                
                # Persist results in session state for the UI
                st.session_state.lb = df
                st.session_state.drift = drift
                st.session_state.date = last_date
                
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

# --- RESULTS TABS ---
if 'lb' in st.session_state:
    st.divider()
    
    tab1, tab2 = st.tabs(["🏆 Leaderboard", "⚔️ Rivalries & Matrix"])

    with tab1:
        st.metric("Session Wealth Drift", f"{st.session_state.drift} MMR")
        st.subheader(f"📅 Results for: {st.session_state.date}")
        
        # Player Search Filter
        search = st.text_input("🔍 Search Player:", placeholder="Type a name to filter the ranking...", key="p_search")
        df_disp = st.session_state.lb
        if search:
            df_disp = df_disp[df_disp['Player'].str.contains(search, case=False)]
        
        st.dataframe(df_disp, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("⚔️ Rivalry Lookup")
        st.write("Analyze performance and face-to-face matchups.")
        
        player_list = sorted(st.session_state.lb['Player'].tolist())
        h1, h2 = st.columns(2)
        
        with h1:
            hero = st.selectbox("Select Hero Player:", player_list, key="p1_select")
        with h2:
            rival = st.selectbox("Select Rival Player:", player_list, key="p2_select")
            
        # Action: Direct H2H
        if st.button("Analyze Direct H2H", use_container_width=True):
            engine = FaduMMREngine()
            h2h = engine.get_h2h(input_area, hero, rival)
            
            if h2h and h2h["matches"]:
                st.divider()
                st.write(f"## {hero} {h2h['p1_wins']} - {h2h['p2_wins']} {rival}")
                st.table(pd.DataFrame(h2h["matches"]))
            else:
                st.warning(f"No direct matches found between {hero} and {rival} in these logs.")
        
        st.divider()
        
        # Action: Career Matrix
        st.subheader(f"📊 {hero}'s Opponent Matrix")
        st.caption("A summary of wins/losses against every opponent ever faced.")
        
        if st.button(f"Generate Career Matrix for {hero}", use_container_width=True):
            engine = FaduMMREngine()
            matrix_df = engine.get_rivalry_matrix(input_area, hero)
            
            if matrix_df is not None:
                st.dataframe(matrix_df, use_container_width=True, hide_index=True)
            else:
                st.warning(f"No opponent data found for {hero} in the logs.")