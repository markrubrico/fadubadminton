import pandas as pd
import numpy as np
import re
import config 

class FaduMMREngine:
    def __init__(self):
        # 1. Initialize with seeds from config
        self.seeds = [self.clean_name(s).lower() for s in config.SEEDS]
        self.players = {}
        self.wealth_drift = 0

    def clean_name(self, name):
        """Standardizes name format for consistent matching."""
        return str(name).strip().replace("  ", " ").replace(" ", "")

    def get_tier(self, mmr):
        """Maps MMR to MLBB-style Tiers from config."""
        for name, threshold in config.TIER_THRESHOLDS:
            if mmr >= threshold: return name
        return "Master"

    def _generate_remark(self, p, apd, aod, rank):
        """Dynamic Power Remarks based on performance metrics."""
        if p.get('is_new_debut'): return "🆕 New Player debut. Welcome!"
        if rank == 1: return "The Final Boss. Absolute League Dominance."
        if p.get('win_streak', 0) >= 3: return f"Heat Check! {p['win_streak']} Win Streak."
        if apd < -250: return "Elite Anchor. Carrying the load."
        if aod > 1700: return "Iron Man. Battling heavyweights."
        return "Pure Hustle. Consistent force."

    def get_rivalry_matrix(self, text, target_player):
        """Generates a win/loss matrix against every opponent."""
        if not target_player: return None
        target = self.clean_name(target_player).lower()
        matrix = {}
        logs = self._parse_to_list(text)
        for g in logs:
            wk = [self.clean_name(n).lower() for n in g['W']]
            lk = [self.clean_name(n).lower() for n in g['L']]
            if target in wk:
                for opp in lk:
                    opp_name = opp.title()
                    if opp_name not in matrix: matrix[opp_name] = {"Wins": 0, "Losses": 0}
                    matrix[opp_name]["Wins"] += 1
            if target in lk:
                for opp in wk:
                    opp_name = opp.title()
                    if opp_name not in matrix: matrix[opp_name] = {"Wins": 0, "Losses": 0}
                    matrix[opp_name]["Losses"] += 1
        if not matrix: return None
        df = pd.DataFrame.from_dict(matrix, orient='index').reset_index()
        df.columns = ["Opponent", "Wins", "Losses"]
        df["Total"] = df["Wins"] + df["Losses"]
        df["Win Rate"] = (df["Wins"] / df["Total"]).map(lambda n: f"{n:.0%}")
        return df.sort_values(by=["Total", "Wins"], ascending=False)

    def get_h2h(self, text, p1_name, p2_name):
        """Direct Face-to-Face matchup lookup."""
        if not p1_name or not p2_name: return None
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
        """Parses log text into structured dicts."""
        logs = []; cur_date = "Unknown"
        for line in text.strip().split('\n'):
            date_m = re.match(r'^(\d{1,2}-[A-Za-z]+)', line.strip())
            if date_m: cur_date = date_m.group(1)
            elif 'W:' in line and '|' in line:
                try:
                    p = line.split('|')
                    logs.append({'date': cur_date, 'W': [x.strip() for x in p[0].split('W:')[1].split(',')], 'L': [x.strip() for x in p[1].split('L:')[1].split(',')]})
                except: continue
        return logs

    def simulate(self, text):
        """Runs simulation with fix for New Player tagging and Record resets."""
        if not text.strip(): return pd.DataFrame(), "None", 0
        logs = self._parse_to_list(text)
        if not logs: return pd.DataFrame(), "Unknown", 0
        
        dates = list(dict.fromkeys([l['date'] for l in logs]))
        num_dates = len(dates)

        for idx, d in enumerate(dates):
            is_last_date = (idx == num_dates - 1)
            
            # Record current total games BEFORE this session to detect newcomers
            for p in self.players.values():
                p['total_games_before_session'] = p['wins'] + p['losses']
                p['active_this_date'] = False
                p['s_w'], p['s_l'] = 0, 0
            
            session_games = [x for x in logs if x['date'] == d]
            for g in session_games:
                wk = [self._init_p(n) for n in g['W']]
                lk = [self._init_p(n) for n in g['L']]
                
                cur_mmrs = [p['mmr'] for p in self.players.values()]
                thresh = np.percentile(cur_mmrs, 80) if cur_mmrs else 1500

                # --- WINNER LOGIC ---
                for i, n in enumerate(wk):
                    p = self.players[n]; opps = [self.players[l]['mmr'] for l in lk]
                    if not p['active_this_date']: 
                        p['mmr_start_of_day'] = p['mmr']
                        p['active_this_date'] = True
                        # Tag as New only if they had 0 games before the very last date
                        if is_last_date and p.get('total_games_before_session', 0) == 0:
                            p['is_new_debut'] = True
                        else:
                            p['is_new_debut'] = False
                    
                    bonus = 0
                    gap = max(opps) - p['mmr']
                    if p['mmr'] < 1349 and gap >= 300:
                        bonus = min(gap * 0.25, 80)
                    
                    gain = 40 + bonus
                    p['mmr'] += gain; p['wins'] += 1; p['s_w'] += 1; p['win_streak'] += 1
                    p['peak'] = max(p['peak'], p['mmr'])
                    p['t_opp'] += (sum(opps)/2)
                    p['t_p_delta'] += (self.players[wk[1-i]]['mmr'] - p['mmr'])
                    self.wealth_drift += gain

                # --- LOSER LOGIC ---
                for i, n in enumerate(lk):
                    l = self.players[n]; part = self.players[lk[1-i]]
                    if not l['active_this_date']: 
                        l['mmr_start_of_day'] = l['mmr']
                        l['active_this_date'] = True
                        if is_last_date and l.get('total_games_before_session', 0) == 0:
                            l['is_new_debut'] = True
                        else:
                            l['is_new_debut'] = False
                    
                    loss = 10 if (l['wins'] + l['losses']) < config.ROOKIE_SHIELD_GAMES else 20
                    gap = l['mmr'] - part['mmr']
                    if (l['mmr'] >= thresh and gap >= config.GUARDIAN_SHIELD_THRESHOLD) or \
                       (part['mmr'] >= thresh and (part['mmr'] - l['mmr']) >= config.GUARDIAN_SHIELD_THRESHOLD):
                        loss = 16
                    
                    l['mmr'] -= loss
                    if l['peak'] >= config.LEGACY_FLOOR_PEAK: 
                        l['mmr'] = max(l['mmr'], config.LEGACY_FLOOR_MIN)
                    
                    l['losses'] += 1; l['s_l'] += 1; l['win_streak'] = 0
                    l['t_opp'] += (sum([self.players[w]['mmr'] for w in wk])/2)
                    l['t_p_delta'] += (part['mmr'] - l['mmr'])
                    self.wealth_drift -= loss

        return self._build_table(thresh), dates[-1], self.wealth_drift

    def _init_p(self, name):
        """Initializes player if not exist. Does not reset totals."""
        n = self.clean_name(name).lower()
        if n not in self.players:
            start = 1500 if n in self.seeds else 1000
            self.players[n] = {
                'name': name.strip(), 'mmr': start, 'peak': start, 'wins': 0, 'losses': 0, 
                't_opp': 0, 't_p_delta': 0, 'mmr_start_of_day': start, 's_w': 0, 's_l': 0, 
                'active_this_date': False, 'win_streak': 0, 'total_games_before_session': 0,
                'is_new_debut': False
            }
        return n

    def _build_table(self, thresh):
        res = []
        for p in self.players.values():
            tot = p['wins'] + p['losses']
            if tot == 0: continue
            aod, apd = round(p['t_opp']/tot), round(p['t_p_delta']/tot)
            res.append({
                "Rank": 0, "Player": p['name'], "Tier": self.get_tier(p['mmr']), 
                "MMR": int(round(p['mmr'])), "Peak": int(round(p['peak'])), 
                "+/-": int(round(p['mmr'] - p['mmr_start_of_day'])) if p['active_this_date'] else 0, 
                "AOD": aod, "APD": apd, "Status": "Elite" if p['mmr'] >= thresh else "Stable", 
                "Confidence": "⭐⭐⭐" if tot > 15 else "⭐⭐" if tot > 5 else "⭐", 
                "Last Session": f"{p['s_w']}-{p['s_l']} ", 
                "Season Record": f"{p['wins']}-{p['losses']} ", 
                "Remarks": "", "w_sort": p['wins'], "key": p['name'].lower()
            })
        df = pd.DataFrame(res).sort_values(by=["MMR", "w_sort"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        for i, row in df.iterrows():
            df.at[i, "Remarks"] = self._generate_remark(self.players[row['key']], row['APD'], row['AOD'], row['Rank'])
        return df.drop(columns=['w_sort', 'key'])