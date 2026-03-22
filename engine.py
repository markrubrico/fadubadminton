import pandas as pd
import numpy as np
import re
import config 

class FaduMMREngine:
    """
    Fadu MMR Engine v1.2.0
    ----------------------
    This document serves as the deterministic logic core for the Fadu Badminton 
    Power Rankings. It implements the following Master Specification v4.4 rules:
    
    1. INACTIVITY DECAY: -50 MMR penalty after 3 missed sessions (Rust Rule).
    2. SHIELD PROTECTION: Rookie Shield (Games < 5) and Guardian 2.0 (Elite).
    3. UNDERDOG INJECTION: Lambda-weighted bonuses for low-MMR upsets.
    4. LEGACY FLOOR: 2300 Peak ensures a 1900 MMR hard-floor protection.
    5. UI FILTERING: Internal keys for 'Total Games', 'Missed Sessions', and 'Is_Present'.
    """

    def __init__(self):
        """
        Initialize the engine by loading seeded players from config.py.
        Names are standardized immediately to prevent whitespace mismatches.
        """
        self.seeds = [self.clean_name(s).lower() for s in config.SEEDS]
        self.players = {}
        self.wealth_drift = 0

    def clean_name(self, name):
        """
        Standardizes name format for consistent dictionary key matching.
        Removes leading/trailing whitespace and merges double spaces.
        """
        if not name:
            return ""
        # The .replace("  ", " ") handles common manual entry typos in logs.
        return str(name).strip().replace("  ", " ").replace(" ", "")

    def get_tier(self, mmr):
        """
        Maps numerical MMR to Mobile Legends: Bang Bang style Tiers.
        Thresholds are sourced from the central config file.
        """
        for name, threshold in config.TIER_THRESHOLDS:
            if mmr >= threshold:
                return name
        return "Master"

    def _generate_remark(self, p, apd, aod, rank):
        """
        Generates qualitative adjectives for the Power Ranking Remarks column.
        Logic follows a hierarchy: New Debut -> Rust -> Rank 1 -> Stats.
        """
        # 1. NEW PLAYER DETECTION
        if p.get('is_new_debut'):
            return "🆕 New Player debut. Welcome!"
            
        # 2. INACTIVITY / RUST DETECTION
        missed = p.get('missed_sessions', 0)
        if missed > 3:
            return f"⚠️ RUST: Inactive for {missed} sessions."
            
        # 3. LEADERBOARD TOP SPOT
        if rank == 1:
            return "The Final Boss. Absolute League Dominance."
        
        # 4. HOT STREAKS
        if p.get('win_streak', 0) >= 3:
            return f"Heat Check! {p['win_streak']} Win Streak."
            
        # 5. STATISTICAL OUTLIERS (APD/AOD)
        if apd < -250:
            return "Elite Anchor. Carrying the load."
            
        if aod > 1700:
            return "Iron Man. Battling heavyweights."
            
        return "Pure Hustle. Consistent force."

    def get_rivalry_matrix(self, text, target_player):
        """
        Scans all logs to build a win/loss matrix against every unique opponent.
        Used for the 'Career Matrix' feature in the Streamlit UI.
        """
        if not target_player:
            return None
            
        target = self.clean_name(target_player).lower()
        matrix = {}
        logs = self._parse_to_list(text)
        
        for game in logs:
            winners = [self.clean_name(n).lower() for n in game['W']]
            losers = [self.clean_name(n).lower() for n in game['L']]
            
            # If target won, log the losers as opponents defeated
            if target in winners:
                for opp in losers:
                    opp_name = opp.title()
                    if opp_name not in matrix:
                        matrix[opp_name] = {"Wins": 0, "Losses": 0}
                    matrix[opp_name]["Wins"] += 1
            
            # If target lost, log the winners as opponents lost to
            elif target in losers:
                for opp in winners:
                    opp_name = opp.title()
                    if opp_name not in matrix:
                        matrix[opp_name] = {"Wins": 0, "Losses": 0}
                    matrix[opp_name]["Losses"] += 1
                    
        if not matrix:
            return None
            
        # Convert the dictionary to a DataFrame for UI display
        df = pd.DataFrame.from_dict(matrix, orient='index').reset_index()
        df.columns = ["Opponent", "Wins", "Losses"]
        df["Total"] = df["Wins"] + df["Losses"]
        df["Win Rate"] = (df["Wins"] / df["Total"]).map(lambda n: f"{n:.0%}")
        
        return df.sort_values(by=["Total", "Wins"], ascending=False)

    def get_h2h(self, text, p1_name, p2_name):
        """
        Performs a direct Head-to-Head (H2H) lookup between two specific names.
        Returns wins, losses, and a specific list of match dates.
        """
        if not p1_name or not p2_name:
            return None
            
        p1 = self.clean_name(p1_name).lower()
        p2 = self.clean_name(p2_name).lower()
        
        h2h_stats = {"p1_wins": 0, "p2_wins": 0, "matches": []}
        logs = self._parse_to_list(text)
        
        for game in logs:
            wk = [self.clean_name(n).lower() for n in game['W']]
            lk = [self.clean_name(n).lower() for n in game['L']]
            
            # Check if P1 won vs P2
            if p1 in wk and p2 in lk:
                h2h_stats["p1_wins"] += 1
                h2h_stats["matches"].append({"Date": game['date'], "Winner": p1_name, "Loser": p2_name})
            
            # Check if P2 won vs P1
            elif p2 in wk and p1 in lk:
                h2h_stats["p2_wins"] += 1
                h2h_stats["matches"].append({"Date": game['date'], "Winner": p2_name, "Loser": p1_name})
                
        return h2h_stats

    def _parse_to_list(self, text):
        """
        The parser: Converts raw multi-line strings into structured dictionaries.
        Detects dates via Regex and splits W/L teams via the pipe '|' symbol.
        """
        logs = []
        current_date = "Unknown"
        
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Look for session dates (e.g., 20-Feb)
            date_match = re.match(r'^(\d{1,2}-[A-Za-z]+)', line)
            if date_match:
                current_date = date_match.group(1)
            elif 'W:' in line and '|' in line:
                try:
                    parts = line.split('|')
                    win_names = parts[0].split('W:')[1].split(',')
                    lose_names = parts[1].split('L:')[1].split(',')
                    
                    logs.append({
                        'date': current_date, 
                        'W': [x.strip() for x in win_names], 
                        'L': [x.strip() for x in lose_names]
                    })
                except Exception:
                    # Skip malformed lines to prevent simulation crashes
                    continue
        return logs

    def simulate(self, text):
        """
        THE CORE SIMULATION: Processes all games chronologically.
        Calculates MMR gains, losses, shields, and rust decay.
        """
        if not text.strip():
            return pd.DataFrame(), "None", 0, []
            
        logs = self._parse_to_list(text)
        if not logs:
            return pd.DataFrame(), "Unknown", 0, []
        
        dates = list(dict.fromkeys([l['date'] for l in logs]))
        num_dates = len(dates)
        decay_report = []

        # Iterate through every unique session date
        for idx, d in enumerate(dates):
            is_last_date = (idx == num_dates - 1)
            players_today = set()
            session_games = [x for x in logs if x['date'] == d]
            
            # Identify which players are active in THIS specific session
            for g in session_games:
                all_active = g['W'] + g['L']
                players_today.update([self.clean_name(n).lower() for n in all_active])

            # --- PRE-SESSION LOGIC: RUST CHECK (DECAY) ---
            for p_id, p in self.players.items():
                # Store pre-session stats for +/- calculations
                p['total_games_before_session'] = p['wins'] + p['losses']
                p['active_this_date'] = False
                p['s_w'], p['s_l'] = 0, 0
                
                # Check for inactivity
                if p_id not in players_today:
                    p['missed_sessions'] += 1
                    # Decay starts after 3 missed sessions
                    if p['missed_sessions'] > 3:
                        penalty = 50
                        # Protection: Decay cannot drop a player below their seed MMR
                        starting_floor = 1500 if p_id in self.seeds else 1000
                        p['mmr'] = max(p['mmr'] - penalty, starting_floor)
                        self.wealth_drift -= penalty
                        
                        # Only report decay if it happened on the final log date
                        if is_last_date:
                            decay_report.append({"Player": p['name'], "Penalty": -penalty, "Missed": p['missed_sessions']})
                else:
                    # Player is present today: Reset rust counter
                    p['missed_sessions'] = 0

            # --- SESSION LOGIC: GAME PROCESSING ---
            for game in session_games:
                winners = [self._init_p(n) for n in game['W']]
                losers = [self._init_p(n) for n in game['L']]
                
                # Determine the 'Elite' benchmark for the current pool
                all_scores = [p['mmr'] for p in self.players.values()]
                elite_thresh = np.percentile(all_scores, 80) if all_scores else 1500

                # A. PROCESS WINNERS
                for i, name in enumerate(winners):
                    p = self.players[name]
                    opps = [self.players[l]['mmr'] for l in losers]
                    
                    if not p['active_this_date']: 
                        p['mmr_start_of_day'] = p['mmr']
                        p['active_this_date'] = True
                        # Detect Rookies on their debut date only
                        p['is_new_debut'] = True if (is_last_date and p.get('total_games_before_session', 0) == 0) else False
                    
                    # 1. UNDERDOG BONUS
                    bonus = 0
                    max_opp_mmr = max(opps)
                    gap = max_opp_mmr - p['mmr']
                    if p['mmr'] < 1349 and gap >= 300:
                        bonus = min(gap * 0.25, 80)
                    
                    # 2. APPLY MMR GAIN
                    gain = 40 + bonus
                    p['mmr'] += gain
                    p['wins'] += 1
                    p['s_w'] += 1
                    p['win_streak'] += 1
                    p['peak'] = max(p['peak'], p['mmr'])
                    p['t_opp'] += (sum(opps) / 2)
                    p['t_p_delta'] += (self.players[winners[1-i]]['mmr'] - p['mmr'])
                    self.wealth_drift += gain

                # B. PROCESS LOSERS
                for i, name in enumerate(losers):
                    l = self.players[name]
                    partner = self.players[losers[1-i]]
                    
                    if not l['active_this_date']: 
                        l['mmr_start_of_day'] = l['mmr']
                        l['active_this_date'] = True
                        l['is_new_debut'] = True if (is_last_date and l.get('total_games_before_session', 0) == 0) else False
                    
                    # 1. ROOKIE SHIELD (-10 instead of -20 for first 5 games)
                    loss = 10 if (l['wins'] + l['losses']) < config.ROOKIE_SHIELD_GAMES else 20
                    
                    # 2. GUARDIAN SHIELD (Elite Mitigation)
                    is_elite_game = l['mmr'] >= elite_thresh or partner['mmr'] >= elite_thresh
                    mmr_gap = abs(l['mmr'] - partner['mmr'])
                    if is_elite_game and mmr_gap >= config.GUARDIAN_SHIELD_THRESHOLD:
                        loss = 16
                    
                    # 3. APPLY MMR LOSS
                    l['mmr'] -= loss
                    
                    # 4. LEGACY FLOOR (Mythic 2300 Peak ensures 1900 floor)
                    if l['peak'] >= config.LEGACY_FLOOR_PEAK: 
                        l['mmr'] = max(l['mmr'], config.LEGACY_FLOOR_MIN)
                    
                    l['losses'] += 1
                    l['s_l'] += 1
                    l['win_streak'] = 0
                    l['t_opp'] += (sum([self.players[w]['mmr'] for w in winners]) / 2)
                    l['t_p_delta'] += (partner['mmr'] - l['mmr'])
                    self.wealth_drift -= loss

        # Final return includes the leaderboard table, latest date, wealth drift, and decay report
        return self._build_table(elite_thresh), dates[-1], self.wealth_drift, decay_report

    def _init_p(self, name):
        """
        Initializes a player dictionary if they haven't been seen before.
        Determines starting MMR (1500 or 1000) based on seed status.
        """
        n = self.clean_name(name).lower()
        if n not in self.players:
            start_mmr = 1500 if n in self.seeds else 1000
            self.players[n] = {
                'name': name.strip(), 'mmr': start_mmr, 'peak': start_mmr, 
                'wins': 0, 'losses': 0, 't_opp': 0, 't_p_delta': 0, 
                'mmr_start_of_day': start_mmr, 's_w': 0, 's_l': 0, 
                'active_this_date': False, 'win_streak': 0, 
                'total_games_before_session': 0, 'is_new_debut': False, 
                'missed_sessions': 0
            }
        return n

    def _build_table(self, thresh):
        """
        Compiles the master dataframe for UI display.
        This method includes the hidden columns used for sidebar filtering.
        """
        res = []
        for p in self.players.values():
            total = p['wins'] + p['losses']
            if total == 0:
                continue
            
            # Prepare result dictionary for the DataFrame
            res.append({
                "Rank": 0, 
                "Player": p['name'], 
                "Tier": self.get_tier(p['mmr']), 
                "MMR": int(round(p['mmr'])), 
                "Peak": int(round(p['peak'])), 
                "+/-": int(round(p['mmr'] - p['mmr_start_of_day'])) if p['active_this_date'] else 0, 
                "AOD": round(p['t_opp'] / total), 
                "APD": round(p['t_p_delta'] / total), 
                "Status": "Elite" if p['mmr'] >= thresh else "Stable", 
                "Confidence": "⭐⭐⭐" if total > 15 else "⭐⭐" if total > 5 else "⭐", 
                "Last Session": f"{p['s_w']}-{p['s_l']} ", 
                "Season Record": f"{p['wins']}-{p['losses']} ", 
                "Remarks": "", 
                "w_sort": p['wins'], 
                "key": p['name'].lower(),
                # --- INTERNAL UI COLUMNS (V1.2.0) ---
                "Total_Games": total, 
                "Missed_Sessions": p['missed_sessions'],
                "Is_Present": p['active_this_date']
            })
            
        # Final sort and ranking assignment
        df = pd.DataFrame(res).sort_values(by=["MMR", "w_sort"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        
        # Populate Remarks based on final rankings
        for i, row in df.iterrows():
            player_object = self.players[row['key']]
            df.at[i, "Remarks"] = self._generate_remark(player_object, row['APD'], row['AOD'], row['Rank'])
            
        return df.drop(columns=['w_sort', 'key'])