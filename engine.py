import pandas as pd
import numpy as np
import re
import config 

class FaduMMREngine:
    """
    Fadu MMR Engine v1.4.2
    ----------------------
    The deterministic logic core for the Fadu Badminton Power Rankings. 
    Implements Master Specification v4.4:
    
    1.  STAMINA ANALYSIS: Performance by session phase.
    2.  FORCE MULTIPLIER: Net MMR Impact (APD).
    3.  SYNERGY MATRIX: Partner win/loss tracking.
    4.  CUMULATIVE DECAY: Session-over-session drift.
    5.  INACTIVITY DECAY: The -50 MMR Rust Rule.
    6.  SHIELD PROTECTION: Rookie Shield and Guardian 2.0.
    7.  UNDERDOG INJECTION: Lambda-weighted upset bonuses.
    8.  LEGACY FLOOR: 2300 Peak/1900 Floor protection.
    9.  UI FILTERING: Session presence and game volume keys.
    10. CAREER LEDGER: Historic replay for promotion logs.
    11. HALL OF FAME: Tracking Peaks, Streaks, and Underdog Wins.
    12. ARCHETYPES: Playstyle classification.
    """

    def __init__(self):
        """
        Initialize the engine with standardized seed names from config.
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
            
        # Standardizing whitespace prevents "Jerico" vs "Jerico " mismatches.
        return str(name).strip().replace("  ", " ").replace(" ", "")

    def get_tier(self, mmr):
        """
        Maps numerical MMR to Tier labels (Master -> Mythic Glory).
        Thresholds are defined in config.py.
        """
        for name, threshold in config.TIER_THRESHOLDS:
            if mmr >= threshold:
                return name
        return "Master"

    def _determine_archetype(self, p, apd, aod, total, avg_games):
        """
        CALIBRATED v1.4.2: Matches current league skill distribution.
        Determines the 'Hero Class' for a player based on career stats.
        """
        if total == 0:
            return "Unranked"
            
        win_rate = p['wins'] / total
        
        # 1. THE GENERAL: High Tier leaders who lift partners.
        if p['mmr'] >= 1800 and apd > 40:
            return "🎖️ The General"
            
        # 2. THE CATALYST: High APD (Floor Raisers).
        if apd > 80:
            return "🧪 The Catalyst"
            
        # 3. THE TANK: High AOD (Facing the hardest opponents).
        if aod > 1650:
            return "🛡️ The Tank"
            
        # 4. THE GIANT SLAYER: High volume of underdog victories.
        # Underdog Wins are triggered by beating 300+ MMR gaps.
        if p.get('underdog_wins', 0) >= 2:
            return "⚔️ Giant Slayer"
            
        # 5. THE FINISHER: Peak session performance (Clutch streaks).
        if p.get('max_streak', 0) >= 4:
            return "🔥 The Finisher"
            
        # 6. IRON MAN: High session participation (Gym Rats).
        if total > (avg_games * 1.3):
            return "🦾 Iron Man"
            
        # 7. THE SPECIALIST: Win percentage efficiency.
        if win_rate > 0.58:
            return "🎯 The Specialist"
            
        # 8. THE ROOKIE: Calibration phase.
        if total < config.ROOKIE_SHIELD_GAMES:
            return "🐣 New Challenger"
            
        # 9. DEFAULT: Backbone of the community.
        return "🏸 Consistent Force"

    def _generate_remark(self, p, apd, aod, rank):
        """
        Generates contextual remarks for the Power Rankings table.
        """
        if p.get('is_new_debut'):
            return "🆕 New Player debut. Welcome!"
            
        missed = p.get('missed_sessions', 0)
        if missed > 3:
            return f"⚠️ RUST: Inactive for {missed} sessions."
            
        if rank == 1:
            return "The Final Boss. Absolute League Dominance."
        
        if p.get('win_streak', 0) >= 3:
            return f"Heat Check! {p['win_streak']} Win Streak."
            
        if apd < -250:
            return "Elite Anchor. Carrying the load."
            
        if aod > 1700:
            return "Iron Man. Battling heavyweights."
            
        return "Pure Hustle. Consistent force."

    def get_player_history(self, text, target_player):
        """
        CAREER REPLAY ENGINE:
        Chronologically simulates every game to build a promotion log 
        and rank transition history for a single player.
        """
        if not target_player or not text.strip():
            return None
            
        target_id = self.clean_name(target_player).lower()
        logs = self._parse_to_list(text)
        
        if not logs:
            return None
        
        # State tracking for the replay
        replay_players = {}
        ledger = []
        
        def init_replay_p(name):
            n = self.clean_name(name).lower()
            if n not in replay_players:
                start_mmr = 1500 if n in self.seeds else 1000
                replay_players[n] = {
                    'name': name.strip(), 
                    'mmr': start_mmr, 
                    'peak': start_mmr, 
                    'wins': 0, 
                    'losses': 0, 
                    'current_streak': 0, 
                    'max_streak': 0
                }
            return n

        dates = list(dict.fromkeys([l['date'] for l in logs]))
        
        for d in dates:
            session_games = [x for x in logs if x['date'] == d]
            players_today = set()
            
            for g in session_games:
                players_today.update([self.clean_name(n).lower() for n in (g['W'] + g['L'])])
            
            # --- OFF-COURT DECAY REPLAY ---
            for p_id, p in replay_players.items():
                if p_id not in players_today:
                    p.setdefault('missed_sessions', 0)
                    p['missed_sessions'] += 1
                    
                    if p['missed_sessions'] > 3:
                        old_mmr = p['mmr']
                        old_tier = self.get_tier(old_mmr)
                        
                        floor = 1500 if p_id in self.seeds else 1000
                        p['mmr'] = max(p['mmr'] - 50, floor)
                        p['current_streak'] = 0 
                        
                        if p_id == target_id and (old_mmr - p['mmr']) > 0:
                            new_tier = self.get_tier(p['mmr'])
                            change_log = f"🔽 Demoted to {new_tier}" if old_tier != new_tier else "-"
                            
                            ledger.append({
                                "Date": d, 
                                "Match": "OFF-COURT", 
                                "Event": "📉 RUST DECAY",
                                "Partner": "-", 
                                "Opponents": "Inactivity", 
                                "Result": "Penalty",
                                "Delta": -50, 
                                "Balance": int(round(p['mmr'])),
                                "Tier": new_tier, 
                                "Rank Status": change_log
                            })
                else:
                    p['missed_sessions'] = 0

            # --- MATCH REPLAY ---
            for game in session_games:
                winners = [init_replay_p(n) for n in game['W']]
                losers = [init_replay_p(n) for n in game['L']]
                
                all_scores = [p['mmr'] for p in replay_players.values()]
                elite_thresh = np.percentile(all_scores, 80) if all_scores else 1500
                
                # Winner Logic
                for i, name in enumerate(winners):
                    p = replay_players[name]
                    old_mmr = p['mmr']
                    old_tier = self.get_tier(old_mmr)
                    
                    bonus = 0
                    opp_max = max([replay_players[l]['mmr'] for l in losers])
                    gap = opp_max - p['mmr']
                    
                    # Underdog check (v1.4.2: Tier Ceiling Removed)
                    if gap >= 300:
                        bonus = min(gap * 0.25, 80)
                    
                    gain = 40 + bonus
                    p['mmr'] += gain
                    p['wins'] += 1
                    p['current_streak'] += 1
                    p['max_streak'] = max(p['max_streak'], p['current_streak'])
                    p['peak'] = max(p['peak'], p['mmr'])
                    
                    if name == target_id:
                        new_tier = self.get_tier(p['mmr'])
                        change_log = f"🔼 Promoted to {new_tier}" if old_tier != new_tier else "-"
                        partner = [n for n in game['W'] if self.clean_name(n).lower() != target_id][0]
                        opps = " / ".join(game['L'])
                        
                        ledger.append({
                            "Date": d, 
                            "Match": f"Game {game.get('game_num', '?')}", 
                            "Event": "Victory" if bonus == 0 else "🔥 Underdog Win",
                            "Partner": partner, 
                            "Opponents": opps, 
                            "Result": "W",
                            "Delta": f"+{int(gain)}", 
                            "Balance": int(round(p['mmr'])),
                            "Tier": new_tier, 
                            "Rank Status": change_log
                        })

                # Loser Logic
                for i, name in enumerate(losers):
                    l = replay_players[name]
                    old_mmr = l['mmr']
                    old_tier = self.get_tier(old_mmr)
                    
                    partner_obj = replay_players[losers[1-i]]
                    loss = 10 if (l['wins'] + l['losses']) < config.ROOKIE_SHIELD_GAMES else 20
                    
                    is_elite = l['mmr'] >= elite_thresh or partner_obj['mmr'] >= elite_thresh
                    mmr_gap = abs(l['mmr'] - partner_obj['mmr'])
                    
                    if is_elite and mmr_gap >= config.GUARDIAN_SHIELD_THRESHOLD:
                        loss = 16
                    
                    l['mmr'] -= loss
                    l['losses'] += 1
                    l['current_streak'] = 0
                    
                    if l['peak'] >= config.LEGACY_FLOOR_PEAK:
                        l['mmr'] = max(l['mmr'], config.LEGACY_FLOOR_MIN)
                    
                    if name == target_id:
                        new_tier = self.get_tier(l['mmr'])
                        change_log = f"🔽 Demoted to {new_tier}" if old_tier != new_tier else "-"
                        partner_name = [n for n in game['L'] if self.clean_name(n).lower() != target_id][0]
                        opps = " / ".join(game['W'])
                        
                        ledger.append({
                            "Date": d, 
                            "Match": f"Game {game.get('game_num', '?')}", 
                            "Event": "Defeat" if loss == 20 else "🛡️ Shielded Loss",
                            "Partner": partner_name, 
                            "Opponents": opps, 
                            "Result": "L",
                            "Delta": f"-{int(loss)}", 
                            "Balance": int(round(l['mmr'])),
                            "Tier": new_tier, 
                            "Rank Status": change_log
                        })

        return pd.DataFrame(ledger[::-1]) if ledger else None

    def get_stamina_analysis(self, text, target_player):
        """
        Analyzes win rates across session phases to detect fatigue.
        """
        if not target_player:
            return None
            
        target = self.clean_name(target_player).lower()
        logs = self._parse_to_list(text)
        
        brackets = {
            "Fresh (1-5)": {"W": 0, "L": 0}, 
            "Warm (6-10)": {"W": 0, "L": 0}, 
            "Peak (11-15)": {"W": 0, "L": 0}, 
            "Fatigued (16+)": {"W": 0, "L": 0}
        }
        
        for game in logs:
            wk = [self.clean_name(n).lower() for n in game['W']]
            lk = [self.clean_name(n).lower() for n in game['L']]
            num = game.get('game_num', 1)
            
            p = "Fresh (1-5)" if num <= 5 else "Warm (6-10)" if num <= 10 else "Peak (11-15)" if num <= 15 else "Fatigued (16+)"
            
            if target in wk:
                brackets[p]["W"] += 1
            elif target in lk:
                brackets[p]["L"] += 1
                
        res = []
        for phase, stats in brackets.items():
            total = stats["W"] + stats["L"]
            if total > 0:
                res.append({
                    "Phase": phase, 
                    "W": stats["W"], 
                    "L": stats["L"], 
                    "Win Rate": f"{(stats['W']/total):.0%}"
                })
                
        return pd.DataFrame(res) if res else None

    def get_teammate_matrix(self, text, target_player):
        """
        Builds synergy matrix and calculates Net MMR Impact (APD).
        """
        if not target_player:
            return None
            
        target = self.clean_name(target_player).lower()
        matrix = {}
        
        for game in self._parse_to_list(text):
            winners = [self.clean_name(n).lower() for n in game['W']]
            losers = [self.clean_name(n).lower() for n in game['L']]
            
            if target in winners:
                for tm in [n for n in winners if n != target]:
                    n = tm.title()
                    matrix.setdefault(n, {"W": 0, "L": 0, "Impact": 0})
                    matrix[n]["W"] += 1
                    matrix[n]["Impact"] += 40
            elif target in losers:
                for tm in [n for n in losers if n != target]:
                    n = tm.title()
                    matrix.setdefault(n, {"W": 0, "L": 0, "Impact": 0})
                    matrix[n]["L"] += 1
                    matrix[n]["Impact"] -= 20
                    
        if not matrix:
            return None
            
        df = pd.DataFrame.from_dict(matrix, orient='index').reset_index()
        df.columns = ["Teammate", "Wins", "Losses", "Net MMR Impact"]
        df["Total Games"] = df["Wins"] + df["Losses"]
        df["Win Rate"] = (df["Wins"] / df["Total Games"]).map(lambda n: f"{n:.0%}")
        
        return df.sort_values(by=["Net MMR Impact"], ascending=False)

    def get_rivalry_matrix(self, text, target_player):
        """
        Tracks win/loss records against every unique opponent.
        """
        if not target_player:
            return None
            
        target = self.clean_name(target_player).lower()
        matrix = {}
        
        for game in self._parse_to_list(text):
            winners = [self.clean_name(n).lower() for n in game['W']]
            losers = [self.clean_name(n).lower() for n in game['L']]
            
            if target in winners:
                for opp in losers:
                    o = opp.title()
                    matrix.setdefault(o, {"Wins": 0, "Losses": 0})
                    matrix[o]["Wins"] += 1
            elif target in losers:
                for opp in winners:
                    o = opp.title()
                    matrix.setdefault(o, {"Wins": 0, "Losses": 0})
                    matrix[o]["Losses"] += 1
                    
        if not matrix:
            return None
            
        df = pd.DataFrame.from_dict(matrix, orient='index').reset_index()
        df.columns = ["Opponent", "Wins", "Losses"]
        df["Total"] = df["Wins"] + df["Losses"]
        df["Win Rate"] = (df["Wins"] / df["Total"]).map(lambda n: f"{n:.0%}")
        
        return df.sort_values(by=["Total", "Wins"], ascending=False)

    def get_h2h(self, text, p1_name, p2_name):
        """
        Direct comparison between two players.
        """
        if not p1_name or not p2_name:
            return None
            
        p1 = self.clean_name(p1_name).lower()
        p2 = self.clean_name(p2_name).lower()
        
        stats = {"p1_wins": 0, "p2_wins": 0, "matches": []}
        
        for game in self._parse_to_list(text):
            wk = [self.clean_name(n).lower() for n in game['W']]
            lk = [self.clean_name(n).lower() for n in game['L']]
            
            if p1 in wk and p2 in lk:
                stats["p1_wins"] += 1
                stats["matches"].append({"Date": game['date'], "Winner": p1_name, "Loser": p2_name})
            elif p2 in wk and p1 in lk:
                stats["p2_wins"] += 1
                stats["matches"].append({"Date": game['date'], "Winner": p2_name, "Loser": p1_name})
                
        return stats

    def _parse_to_list(self, text):
        """
        Parses raw text logs into structured session/game data.
        """
        logs = []
        current_date = "Unknown"
        
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
                
            # Date detection (e.g., 11-Apr)
            date_match = re.match(r'^(\d{1,2}-[A-Za-z]+)', line)
            if date_match:
                current_date = date_match.group(1)
                continue
            
            # Game index detection
            game_idx_match = re.match(r'^Game\s+(\d+):', line)
            game_idx = int(game_idx_match.group(1)) if game_idx_match else 1
            
            if 'W:' in line and '|' in line:
                try:
                    parts = line.split('|')
                    win_names = parts[0].split('W:')[1].split(',')
                    lose_names = parts[1].split('L:')[1].split(',')
                    
                    logs.append({
                        'date': current_date, 
                        'game_num': game_idx, 
                        'W': [x.strip() for x in win_names], 
                        'L': [x.strip() for x in lose_names]
                    })
                except Exception:
                    continue
        return logs

    def simulate(self, text):
        """
        MAIN CORE: Processes the entire match history for the current session.
        Calculates MMR, decaying, streaks, and Hall of Fame stats.
        """
        if not text.strip():
            return pd.DataFrame(), "None", 0, []
            
        logs = self._parse_to_list(text)
        if not logs:
            return pd.DataFrame(), "Unknown", 0, []
            
        dates = list(dict.fromkeys([l['date'] for l in logs]))
        decay_tracker = {}
        
        for idx, d in enumerate(dates):
            is_last_date = (idx == len(dates) - 1)
            players_today = set()
            session_games = [x for x in logs if x['date'] == d]
            
            # Identify active players for rust check
            for g in session_games:
                players_today.update([self.clean_name(n).lower() for n in g['W'] + g['L']])
            
            # --- RUST & PRESENCE CHECK ---
            for p_id, p in self.players.items():
                p['total_games_before_session'] = p['wins'] + p['losses']
                p['active_this_date'] = False
                p['s_w'], p['s_l'] = 0, 0
                
                if p_id not in players_today:
                    p['missed_sessions'] += 1
                    if p['missed_sessions'] > 3:
                        penalty = 50
                        floor = 1500 if p_id in self.seeds else 1000
                        p['mmr'] = max(p['mmr'] - penalty, floor)
                        p['win_streak'] = 0
                        self.wealth_drift -= penalty
                        decay_tracker[p_id] = decay_tracker.get(p_id, 0) + penalty
                else:
                    p['missed_sessions'] = 0

            # --- PROCESS GAMES ---
            for game in session_games:
                winners = [self._init_p(n) for n in game['W']]
                losers = [self._init_p(n) for n in game['L']]
                
                all_scores = [pl['mmr'] for pl in self.players.values()]
                elite_thresh = np.percentile(all_scores, 80) if self.players else 1500
                
                # Winner Logic
                for i, name in enumerate(winners):
                    p = self.players[name]
                    opps = [self.players[l]['mmr'] for l in losers]
                    
                    if not p['active_this_date']:
                        p['mmr_start_of_day'] = p['mmr']
                        p['active_this_date'] = True
                        p['is_new_debut'] = True if (is_last_date and p.get('total_games_before_session', 0) == 0) else False
                    
                    bonus = 0
                    gap = max(opps) - p['mmr']
                    
                    # Underdog Fix (v1.4.2: Ceiling Removed)
                    if gap >= 300:
                        bonus = min(gap * 0.25, 80)
                        p['underdog_wins'] += 1 # GIANT SLAYER TRACKER
                    
                    gain = 40 + bonus
                    p['mmr'] += gain
                    p['wins'] += 1
                    p['s_w'] += 1
                    p['win_streak'] += 1
                    p['max_streak'] = max(p['max_streak'], p['win_streak']) # MAX STREAK TRACKER
                    p['peak'] = max(p['peak'], p['mmr'])
                    p['t_opp'] += (sum(opps) / 2)
                    p['t_p_delta'] += (self.players[winners[1-i]]['mmr'] - p['mmr'])
                    self.wealth_drift += gain

                # Loser Logic
                for i, name in enumerate(losers):
                    l = self.players[name]
                    partner = self.players[losers[1-i]]
                    
                    if not l['active_this_date']:
                        l['mmr_start_of_day'] = l['mmr']
                        l['active_this_date'] = True
                        l['is_new_debut'] = True if (is_last_date and l.get('total_games_before_session', 0) == 0) else False
                    
                    loss = 10 if (l['wins'] + l['losses']) < config.ROOKIE_SHIELD_GAMES else 20
                    mmr_gap = abs(l['mmr'] - partner['mmr'])
                    
                    if (l['mmr'] >= elite_thresh or partner['mmr'] >= elite_thresh) and mmr_gap >= config.GUARDIAN_SHIELD_THRESHOLD:
                        loss = 16
                    
                    l['mmr'] -= loss
                    l['losses'] += 1
                    l['s_l'] += 1
                    l['win_streak'] = 0
                    
                    if l['peak'] >= config.LEGACY_FLOOR_PEAK:
                        l['mmr'] = max(l['mmr'], config.LEGACY_FLOOR_MIN)
                    
                    l['t_opp'] += (sum([self.players[w]['mmr'] for w in winners]) / 2)
                    l['t_p_delta'] += (partner['mmr'] - l['mmr'])
                    self.wealth_drift -= loss

        decay_report = []
        for p_id, total_penalty in decay_tracker.items():
            decay_report.append({
                "Player": self.players[p_id]['name'], 
                "Penalty": -total_penalty, 
                "Missed": self.players[p_id]['missed_sessions']
            })

        return self._build_table(elite_thresh), dates[-1], self.wealth_drift, decay_report

    def _init_p(self, name):
        """
        Initializes player state with Hall of Fame and Archetype support.
        """
        n = self.clean_name(name).lower()
        if n not in self.players:
            start_mmr = 1500 if n in self.seeds else 1000
            self.players[n] = {
                'name': name.strip(), 
                'mmr': start_mmr, 
                'peak': start_mmr, 
                'wins': 0, 
                'losses': 0, 
                't_opp': 0, 
                't_p_delta': 0, 
                'mmr_start_of_day': start_mmr, 
                's_w': 0, 
                's_l': 0, 
                'active_this_date': False, 
                'win_streak': 0, 
                'max_streak': 0, 
                'underdog_wins': 0, 
                'total_games_before_session': 0, 
                'is_new_debut': False, 
                'missed_sessions': 0
            }
        return n

    def _build_table(self, thresh):
        """
        Compiles the final Power Ranking DataFrame.
        """
        res = []
        all_totals = [p['wins'] + p['losses'] for p in self.players.values() if (p['wins'] + p['losses']) > 0]
        avg_games = np.mean(all_totals) if all_totals else 1
        
        for p in self.players.values():
            total = p['wins'] + p['losses']
            if total == 0:
                continue
                
            apd = round(p['t_p_delta'] / total)
            aod = round(p['t_opp'] / total)
            
            res.append({
                "Rank": 0, 
                "Player": p['name'], 
                "Archetype": self._determine_archetype(p, apd, aod, total, avg_games), 
                "Tier": self.get_tier(p['mmr']), 
                "MMR": int(round(p['mmr'])), 
                "Peak": int(round(p['peak'])), 
                "Max Streak": p['max_streak'], # HALL OF FAME
                "Underdog Wins": p['underdog_wins'], # HALL OF FAME
                "+/-": int(round(p['mmr'] - p['mmr_start_of_day'])) if p['active_this_date'] else 0, 
                "AOD": aod, 
                "APD": apd, 
                "Status": "Elite" if p['mmr'] >= thresh else "Stable", 
                "Confidence": "⭐⭐⭐" if total > 15 else "⭐⭐" if total > 5 else "⭐", 
                "Last Session": f"{p['s_w']}-{p['s_l']} ", 
                "Season Record": f"{p['wins']}-{p['losses']} ", 
                "Remarks": "", 
                "w_sort": p['wins'], 
                "key": p['name'].lower(),
                "Total_Games": total, 
                "Missed_Sessions": p['missed_sessions'], 
                "Is_Present": p['active_this_date']
            })
            
        df = pd.DataFrame(res).sort_values(by=["MMR", "w_sort"], ascending=False)
        df['Rank'] = range(1, len(df) + 1)
        
        for i, row in df.iterrows():
            player_object = self.players[row['key']]
            df.at[i, "Remarks"] = self._generate_remark(player_object, row['APD'], row['AOD'], row['Rank'])
            
        return df.drop(columns=['w_sort', 'key'])