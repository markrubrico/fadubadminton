import streamlit as st
import requests
import pandas as pd
from engine import FaduMMREngine
from auditor import ai_audit_session

# --- DASHBOARD CONFIG ---
st.set_page_config(page_title="Fadu MMR v1.1.0", layout="wide")

with st.sidebar:
    st.title("🏸 Fadu Ops")
    # Connection Status
    if "BRIDGE_URL" in st.secrets: st.success("Registry: 🟢 Online")
    else: st.error("Registry: 🔴 Offline")
    if "GROQ_API_KEY" in st.secrets: st.success("Auditor: 🟢 Online")
    else: st.error("Auditor: 🔴 Offline")
    
    st.divider()
    st.caption("v1.1.0 | Rivalry & Tabs Build")
    st.info("Tip: Head over to the H2H tab after calculating to see player rivalries.")

# --- INPUT AREA ---
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
                
                # Persist results in session state
                st.session_state.lb = df
                st.session_state.drift = drift
                st.session_state.date = last_date
                
                if "BRIDGE_URL" in st.secrets:
                    payload = {"target": "Registry", "headers": df.columns.tolist(), "values": df.values.tolist()}
                    try:
                        resp = requests.post(st.secrets["BRIDGE_URL"], json=payload, timeout=20)
                        st.toast(f"✅ Registry Updated: {resp.text}")
                    except Exception as e:
                        st.error(f"❌ Sync Error: {str(e)}")

# --- RESULTS TABS (The New Core) ---
if 'lb' in st.session_state:
    st.divider()
    
    tab1, tab2 = st.tabs(["🏆 Leaderboard", "⚔️ Head-to-Head"])

    with tab1:
        st.metric("Session Wealth Drift", f"{st.session_state.drift} MMR")
        st.subheader(f"📅 Results for: {st.session_state.date}")
        
        # Player Search Filter
        search = st.text_input("🔍 Search Player:", placeholder="Type a name to filter the ranking...")
        df_disp = st.session_state.lb
        if search:
            df_disp = df_disp[df_disp['Player'].str.contains(search, case=False)]
        
        st.dataframe(df_disp, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("⚔️ Rivalry Lookup")
        st.write("Find out who truly dominates the matchup.")
        
        player_list = sorted(st.session_state.lb['Player'].tolist())
        h1, h2 = st.columns(2)
        
        with h1:
            hero = st.selectbox("Select Player 1:", player_list, key="p1_select")
        with h2:
            rival = st.selectbox("Select Player 2:", player_list, key="p2_select")
            
        if st.button("Analyze Rivalry", use_container_width=True):
            engine = FaduMMREngine()
            h2h = engine.get_h2h(input_area, hero, rival)
            
            if h2h and h2h["matches"]:
                st.divider()
                st.write(f"## {hero} vs {rival}")
                
                m1, m2, m3 = st.columns(3)
                total = h2h["p1_wins"] + h2h["p2_wins"]
                m1.metric(f"{hero} Wins", h2h["p1_wins"])
                m2.metric("Total Meetings", total)
                m3.metric(f"{rival} Wins", h2h["p2_wins"])
                
                # Victory History Table
                st.table(pd.DataFrame(h2h["matches"]))
            else:
                st.warning(f"No matches found in the current logs between {hero} and {rival}.")