import pandas as pd
import numpy as np
import re
import config 

class FaduMMREngine:
    """
    Fadu MMR Engine v1.1.8
    - Fixed return signature to support Decay Heatmaps
    - Includes 2300/1900 Legacy Floor
    - Includes Underdog Bonus (Lambda-based)
    - Includes Rookie & Guardian Shields
    """

    def __init__(self):
        # We clean the seeds from config to prevent whitespace matching errors
        self.seeds = [self.clean_name(s).lower() for s in config.SEEDS]
        self.players = {}
        self.wealth_drift = 0

    def clean_name(self, name):
        """Standardizes name format for consistent matching."""
        if not name:
            return ""
        return str(name).strip().replace("  ", " ").replace(" ", "")

    def get_tier(self, mmr):
        """Maps MMR to Tiers defined in the Ops Manual."""
        for name, threshold in config.TIER_THRESHOLDS:
            if mmr >= threshold:
                return name
        return "Master"

    def _generate_remark(self, p, apd, aod, rank):
        """Dynamic Power Remarks based on performance and activity."""
        # Check for New Player debut
        if p.get('is_new_debut'):
            return "🆕 New Player debut. Welcome!"
            
        # Check for Inactivity Decay (Rust)
        missed = p.get('missed_sessions', 0)
        if missed > 3:
            return f"⚠️ RUST: Inactive for {missed} sessions."
            
        # Performance Based Logic
        if rank == 1:
            return "The Final Boss. Absolute League Dominance."
        
        if p.get('win_streak', 0) >= 3:
            return f"Heat Check! {p['win_streak']} Win Streak."
            
        if apd < -250:
            return "Elite Anchor. Carrying the load."
            
        if aod > 1700:
            return "Iron Man. Battling heavyweights."
            
        return "Pure Hustle. Consistent force."

    def get_rivalry_matrix(self, text, target_player):
        """Generates a win/loss matrix against every unique opponent."""
        if not target_player:
            return None
            
        target = self.clean_name(target_player).lower()
        matrix = {}
        logs = self._parse_to_list(text)
        
        for g in logs:
            wk = [self.clean_name(n).lower() for n in g['W']]
            lk = [self.clean_name(n).lower() for n in g['L']]
            
            if target in wk:
                for opp in lk:
                    opp_name = opp.title()
                    if opp_name not in matrix:
                        matrix[opp_name] = {"Wins": 0, "Losses": 0}
                    matrix[opp_name]["Wins"] += 1
            elif target in lk:
                for opp in wk:
                    opp_name = opp.title()
                    if opp_name not in matrix:
                        matrix[opp_name] = {"Wins": 0, "Losses": 0}
                    matrix[opp_name]["Losses"] += 1
                    
        if not matrix:
            return None
            
        df = pd.DataFrame.from_dict(matrix, orient='index').reset_index()
        df.columns = ["Opponent", "Wins", "Losses"]
        df["Total"] = df["Wins"] + df["Losses"]
        df["Win Rate"] = (df["Wins"] / df["Total"]).map(lambda n: f"{n:.0%}")
        return df.sort_values(by=["Total", "Wins"], ascending=False)

    def get_h2h(self, text, p1_name, p2_name):
        """Scans logs for direct games where P1 and P2 faced off."""
        if not p1_name or not p2_name:
            return None
            
        p1 = self.clean_name(p1_name).lower()
        p2 = self.clean_name(p2_name).lower()
        
        h2h_stats = {"p1_wins": 0, "p2_wins": 0, "matches": []}
        logs = self._parse_to_list(text)
        
        for g in logs:
            wk = [self.clean_name(n).lower() for n in g['W']]
            lk = [self.clean_name(n).lower() for n in g['L']]
            
            if p1 in wk and p2 in lk:
                h2h_stats["p1_wins"] += 1
                h2h_stats["matches"].append({"Date": g['date'], "Winner": p1_name, "Loser": p2_name})
            elif p2 in wk and p1 in lk:
                h2h_stats["p2_wins"] += 1
                h2h_stats["matches"].append({"Date": g['date'], "Winner": p2_name, "Loser": p1_name})
                
        return h2h_stats

    def _parse_to_list(self, text):
        """Parses raw text logs into structured dictionaries."""
        logs = []
        current_date = "Unknown"
        
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            
            date_match = re.match(r'^(\d{1,2}-[A-Za-z]+)', line)
            if date_match:
                current_date = date_match.group(1)
            elif 'W:' in line and '|' in line:
                try:
                    parts = line.split('|')
                    w = [x.strip() for x in parts[0].split('W:')[1].split(',')]
                    l = [x.strip() for x in parts[1].split('L:')[1].split(',')]
                    logs.append({'date': current_date, 'W': w, 'L': l})
                except Exception:
                    continue
        return logs

    def simulate(self, text):
        """Process MMR with support for the 4-value return signature."""
        if not text.strip():
            return pd.DataFrame(), "None", 0, []
            
        logs = self._parse_to_list(text)
        if not logs:
            return pd.DataFrame(), "Unknown", 0, []
        
        dates = list(dict.fromkeys([l['date'] for l in logs]))
        num_dates = len(dates)
        decay_report = []

        for idx, d in enumerate(dates):
            is_last_date = (idx == num_dates - 1)
            players_today = set()
            session_games = [x for x in logs if x['date'] == d]
            
            for g in session_games:
                players_today.update([self.clean_name(n).lower() for n in g['W'] + g['L']])

            # --- PRE-SESSION: APPLY DECAY ---
            for p_id, p in self.players.items():
                p['total_games_before_session'] = p['wins'] + p['losses']
                p['active_this_date'] = False
                p['s_w'], p['s_l'] = 0, 0
                
                if p_id not in players_today:
                    p['missed_sessions'] += 1
                    if p['missed_sessions'] > 3:
                        penalty = 50
                        start_mmr = 1500 if p_id in self.seeds else 1000
                        p['mmr'] = max(p['mmr'] - penalty, start_mmr)
                        self.wealth_drift -= penalty
                        if is_last_date:
                            decay_report.append({"Player": p['name'], "Penalty": -penalty, "Missed": p['missed_sessions']})
                else:
                    p['missed_sessions'] = 0

            # --- SESSION: PROCESS THE GAMES ---
            for g in session_games:
                wk = [self._init_p(n) for n in g['W']]
                lk = [self._init_p(n) for n in g['L']]
                
                cur_scores = [p['mmr'] for p in self.players.values()]
                elite_thresh = np.percentile(cur_scores, 80) if cur_scores else 1500

                # Process Winners
                for i, name in enumerate(wk):
                    p = self.players[name]
                    opps = [self.players[l]['mmr'] for l in lk]
                    if not p['active_this_date']: 
                        p['mmr_start_of_day'] = p['mmr']
                        p['active_this_date'] = True
                        p['is_new_debut'] = True if (is_last_date and p.get('total_games_before_session', 0) == 0) else False
                    
                    # Underdog Bonus
                    bonus = 0
                    gap = max(opps) - p['mmr']
                    if p['mmr'] < 1349 and gap >= 300:
                        bonus = min(gap * 0.25, 80)
                    
                    gain = 40 + bonus
                    p['mmr'] += gain; p['wins'] += 1; p['s_w'] += 1; p['win_streak'] += 1
                    p['peak'] = max(p['peak'], p['mmr'])
                    p['t_opp'] += (sum(opps) / 2); p['t_p_delta'] += (self.players[wk[1-i]]['mmr'] - p['mmr'])
                    self.wealth_drift += gain

                # Process Losers
                for i, name in enumerate(lk):
                    l = self.players[name]; partner = self.players[lk[1-i]]
                    if not l['active_this_date']: 
                        l['mmr_start_of_day'] = l['mmr']
                        l['active_this_date'] = True
                        l['is_new_debut'] = True if (is_last_date and l.get('total_games_before_session', 0) == 0) else False
                    
                    # Base Loss + Rookie Shield
                    loss = 10 if (l['wins'] + l['losses']) < config.ROOKIE_SHIELD_GAMES else 20
                    # Guardian Shield (Elite Logic)
                    if (l['mmr'] >= elite_thresh and (l['mmr'] - partner['mmr']) >= config.GUARDIAN_SHIELD_THRESHOLD) or (partner['mmr'] >= elite_thresh and (partner['mmr'] - l['mmr']) >= config.GUARDIAN_SHIELD_THRESHOLD):
                        loss = 16
                    
                    l['mmr'] -= loss
                    # Legacy Floor Protection
                    if l['peak'] >= config.LEGACY_FLOOR_PEAK: 
                        l['mmr'] = max(l['mmr'], config.LEGACY_FLOOR_MIN)
                    
                    l['losses'] += 1; l['s_l'] += 1; l['win_streak'] = 0
                    l['t_opp'] += (sum([self.players[w]['mmr'] for w in wk]) / 2); l['t_p_delta'] += (partner['mmr'] - l['mmr'])
                    self.wealth_drift -= loss

        return self._build_table(elite_thresh), dates[-1], self.wealth_drift, decay_report

    def _init_p(self, name):
        """Initializes a player profile if missing."""
        n = self.clean_name(name).lower()
        if n not in self.players:
            start = 1500 if n in self.seeds else 1000
            self.players[n] = {
                'name': name.strip(), 'mmr': start, 'peak': start, 'wins': 0, 'losses': 0, 
                't_opp': 0, 't_p_delta': 0, 'mmr_start_of_day': start, 's_w': 0, 's_l': 0, 
                'active_this_date': False, 'win_streak': 0, 'total_games_before_session': 0, 
                'is_new_debut': False, 'missed_sessions': 0
            }
        return n

    def _build_table(self, thresh):
        """Compiles the final Leaderboard table."""
        res = []
        for p in self.players.values():
            total = p['wins'] + p['losses']
            if total == 0: continue
            res.append({
                "Rank": 0, "Player": p['name'], "Tier": self.get_tier(p['mmr']), "MMR": int(round(p['mmr'])), "Peak": int(round(p['peak'])), 
                "+/-": int(round(p['mmr'] - p['mmr_start_of_day'])) if p['active_this_date'] else 0, 
                "AOD": round(p['t_opp'] / total), "APD": round(p['t_p_delta'] / total), 
                "Status": "Elite" if p['mmr'] >= thresh else "Stable", "Confidence": "⭐⭐⭐" if total > 15 else "⭐⭐" if total > 5 else "⭐", 
                "Last Session": f"{p['s_w']}-{p['s_l']} ", "Season Record": f"{p['wins']}-{p['losses']} ", "Remarks": "", "w_sort": p['wins'], "key": p['name'].lower()
            })
        df = pd.DataFrame(res).sort_values(by=["MMR", "w_sort"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        for i, row in df.iterrows():
            df.at[i, "Remarks"] = self._generate_remark(self.players[row['key']], row['APD'], row['AOD'], row['Rank'])
        return df.drop(columns=['w_sort', 'key'])