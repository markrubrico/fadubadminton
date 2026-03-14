import streamlit as st
import requests
from engine import FaduMMREngine
from auditor import ai_audit_session

st.set_page_config(page_title="Fadu MMR v1.0.0", layout="wide")

with st.sidebar:
    st.title("🏸 Fadu Ops")
    if "BRIDGE_URL" in st.secrets: st.success("Registry: 🟢 Online")
    else: st.error("Registry: 🔴 Offline")
    if "GROQ_API_KEY" in st.secrets: st.success("Auditor: 🟢 Online")
    else: st.error("Auditor: 🔴 Offline")
    st.divider(); st.caption("v1.0.0 | Modular Baseline")

input_area = st.text_area("Match Logs Input:", height=300)

c1, c2, _ = st.columns([1.5, 1.5, 4])
with c1:
    if st.button("🔍 Run Session Audit", use_container_width=True):
        if 'audit_report' in st.session_state: del st.session_state['audit_report']
        if not input_area.strip(): st.warning("Paste logs first.")
        else:
            with st.spinner("Phonetic Check..."):
                engine = FaduMMREngine()
                _, _, _ = engine.simulate(input_area) # Initialize roster
                st.session_state.audit_report = ai_audit_session(input_area, list(engine.players.keys()))

if 'audit_report' in st.session_state:
    st.info(f"### 📋 Audit Findings\n{st.session_state.audit_report}")
    if st.button("Close Audit"): del st.session_state.audit_report; st.rerun()

with c2:
    if st.button("🚀 Calculate & Sync", type="primary", use_container_width=True):
        if not input_area.strip(): st.warning("Paste logs first.")
        else:
            with st.spinner("Syncing to Cloud..."):
                engine = FaduMMREngine()
                df, last_date, drift = engine.simulate(input_area)
                st.session_state.lb, st.session_state.drift, st.session_state.date = df, drift, last_date
                if "BRIDGE_URL" in st.secrets:
                    requests.post(st.secrets["BRIDGE_URL"], json={"target": "Registry", "headers": df.columns.tolist(), "values": df.values.tolist()})
                    st.success("🎉 Google Sheet Updated!")

if 'lb' in st.session_state:
    st.divider()
    st.metric("Session Wealth Drift", f"{st.session_state.drift} MMR")
    st.subheader(f"📅 Session: {st.session_state.date}")
    st.dataframe(st.session_state.lb, use_container_width=True, hide_index=True)


# Add this to the bottom of app.py

st.divider()
st.subheader("⚔️ Head-to-Head Rivalry")
tab1, tab2 = st.tabs(["Leaderboard", "H2H Lookup"])

with tab1:
    if 'lb' in st.session_state:
        st.metric("Session Wealth Drift", f"{st.session_state.drift} MMR")
        st.dataframe(st.session_state.lb, use_container_width=True, hide_index=True)

with tab2:
    if 'lb' in st.session_state:
        player_list = sorted(st.session_state.lb['Player'].tolist())
        col1, col2 = st.columns(2)
        
        with col1:
            hero = st.selectbox("Select Player 1:", player_list, index=0)
        with col2:
            rival = st.selectbox("Select Player 2:", player_list, index=1)
            
        if st.button("Analyze Rivalry"):
            engine = FaduMMREngine()
            h2h = engine.get_h2h(input_area, hero, rival)
            
            if h2h and h2h["matches"]:
                total = h2h["p1_wins"] + h2h["p2_wins"]
                st.write(f"### {hero} vs {rival}")
                
                # Big Score Display
                s1, s2, s3 = st.columns(3)
                s1.metric(f"{hero} Wins", h2h["p1_wins"])
                s2.metric("Total Meetings", total)
                s3.metric(f"{rival} Wins", h2h["p2_wins"])
                
                # Progress bar for visual win-rate
                win_rate = h2h["p1_wins"] / total
                st.progress(win_rate, text=f"{hero} Dominance: {win_rate:.0%}")
                
                # Match History Table
                st.table(pd.DataFrame(h2h["matches"]))
            else:
                st.warning("No matches found between these two players yet.")