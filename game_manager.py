import random
import time
import uuid
from threading import Lock

FAULTS = ["Repetition", "Deviation", "SpeechDefect", "Grammar", "Gesticulation", "Qualification", "Pause", "LateStart"]

STATUS_LOBBY = "lobby"
STATUS_RUNNING = "running"
STATUS_AWAITING_DECISION = "awaiting_decision"
STATUS_AWAITING_LETTER = "awaiting_letter"
STATUS_PAUSED = "paused"
STATUS_ENDED = "ended"

class GameError(Exception):
    pass

class Player:
    def __init__(self, pid, name, sid=None):
        self.id = pid
        self.name = name
        self.sid = sid

        self.points = 0
        self.correct_jams = 0
        self.wrong_jams = 0
        self.time_spoken = 0.0
        self.letter_tally = {f: 0 for f in FAULTS}
        self.others = []
        
        self.games_played = 0
        self.games_won = 0
        self.total_points = 0
        self.total_time_spoken = 0.0
        self.total_correct_jams = 0
        self.total_wrong_jams = 0
        self.total_letter_tally = {f: 0 for f in FAULTS}
        self.total_others = []

        self.joined_at = time.time()

    def reset_stats(self):
        # wipe current
        self.points = 0
        self.correct_jams = 0
        self.wrong_jams = 0
        self.time_spoken = 0.0
        self.letter_tally = {f: 0 for f in FAULTS}
        self.others = []
        
    def roll_into_cumulative(self):
        # archive
        self.games_played += 1
        self.total_points += self.points
        self.total_time_spoken += self.time_spoken
        self.total_correct_jams += self.correct_jams
        self.total_wrong_jams += self.wrong_jams
        for k, v in self.letter_tally.items():
            self.total_letter_tally[k] += v
        self.total_others.extend(self.others)

    def compute_score(self, live_extra=0.0):
        return self.points + self.time_spoken + live_extra

    def snapshot(self):
        return {
            "points": self.points,
            "time_spoken": self.time_spoken,
            "correct_jams": self.correct_jams,
            "wrong_jams": self.wrong_jams,
            "letter_tally": dict(self.letter_tally),
            "others": list(self.others),
            "games_played": self.games_played,
            "games_won": self.games_won,
            "total_points": self.total_points,
            "total_time_spoken": self.total_time_spoken,
            "total_correct_jams": self.total_correct_jams,
            "total_wrong_jams": self.total_wrong_jams,
            "total_letter_tally": dict(self.total_letter_tally),
            "total_others": list(self.total_others),
        }

    def restore(self, snap):
        self.points = snap["points"]
        self.time_spoken = snap["time_spoken"]
        self.correct_jams = snap["correct_jams"]
        self.wrong_jams = snap["wrong_jams"]
        self.letter_tally = dict(snap["letter_tally"])
        self.others = list(snap["others"])
        self.games_played = snap.get("games_played", 0)
        self.games_won = snap.get("games_won", 0)
        self.total_points = snap.get("total_points", 0)
        self.total_time_spoken = snap.get("total_time_spoken", 0.0)
        self.total_correct_jams = snap.get("total_correct_jams", 0)
        self.total_wrong_jams = snap.get("total_wrong_jams", 0)
        self.total_letter_tally = dict(snap.get("total_letter_tally", {f: 0 for f in FAULTS}))
        self.total_others = list(snap.get("total_others", []))

    def to_dict(self, speaker_id=None, live_extra=0.0):
        return {
            "id": self.id,
            "name": self.name,
            "score": round(self.compute_score(live_extra), 2),
            "is_speaker": self.id == speaker_id,
        }

    def to_result_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "score": round(self.compute_score(), 2),
            "time_spoken": round(self.time_spoken, 2),
            "correct_jams": self.correct_jams,
            "wrong_jams": self.wrong_jams,
            "letter_tally": dict(self.letter_tally),
            "others_count": len(self.others),
            "others": list(self.others),
        }

    def to_cumulative_dict(self, include_current=True):
        games = self.games_played + (1 if include_current else 0)
        pts = self.total_points + (self.points if include_current else 0)
        t_spk = self.total_time_spoken + (self.time_spoken if include_current else 0)
        c_jams = self.total_correct_jams + (self.correct_jams if include_current else 0)
        w_jams = self.total_wrong_jams + (self.wrong_jams if include_current else 0)
        
        tally = dict(self.total_letter_tally)
        others = list(self.total_others)
        
        if include_current:
            for k, v in self.letter_tally.items():
                tally[k] += v
            others.extend(self.others)

        return {
            "id": self.id,
            "name": self.name,
            "games_played": games,
            "games_won": self.games_won,
            "score": round(pts + t_spk, 2),
            "time_spoken": round(t_spk, 2),
            "correct_jams": c_jams,
            "wrong_jams": w_jams,
            "letter_tally": tally,
            "others_count": len(others),
            "others": others,
        }

class Room:
    def __init__(self, code, host_sid, wrong_pts, correct_pts, duration):
        self.code = code
        self.host_sid = host_sid
        self.game_number = 1

        self.wrong_points = wrong_pts
        self.correct_points = correct_pts
        self.timer_total = float(duration)

        self.remaining = float(duration)
        self.running = False
        self.running_since = None

        self.players = {}
        self.departed = {}
        self.speaker_id = None

        self.pending_buzz = None
        self.pending_speaker = None
        self.awaiting_letter = None

        self.status = STATUS_LOBBY
        self.created_at = time.time()
        self.lock = Lock()

    def get_remaining(self):
        if self.running and self.running_since:
            return max(0.0, self.remaining - (time.time() - self.running_since))
        return max(0.0, self.remaining)

    def _pause(self):
        if self.running and self.running_since:
            elapsed = max(0.0, time.time() - self.running_since)
            self.remaining = max(0.0, self.remaining - elapsed)
            self.running = False
            self.running_since = None
            return round(elapsed, 2)
        return 0.0

    def _resume(self):
        self.running = True
        self.running_since = time.time()

    def player_list(self):
        live_extra = 0.0
        live_pid = None
        if self.running and self.running_since:
            live_pid = self.speaker_id
            live_extra = time.time() - self.running_since

        return [
            p.to_dict(self.speaker_id, live_extra if p.id == live_pid else 0.0)
            for p in self.players.values()
        ]

    def public_state(self):
        return {
            "room_code": self.code,
            "game_number": self.game_number,
            "status": self.status,
            "wrong_points": self.wrong_points,
            "correct_points": self.correct_points,
            "timer_total": self.timer_total,
            "remaining": round(self.get_remaining(), 2),
            "running": self.running,
            "speaker_id": self.speaker_id,
            "players": self.player_list(),
            "pending_buzz": self.pending_buzz,
            "awaiting_letter": self.awaiting_letter,
        }

class GameManager:
    def __init__(self):
        self.rooms = {}
        self._mutex = Lock()

    def _gen_code(self):
        with self._mutex:
            for _ in range(1000):
                code = str(random.randint(100000, 999999))
                if code not in self.rooms:
                    return code
            raise GameError("Room creation failed.")

    def create_room(self, host_sid, wrong_points, correct_points, timer_seconds):
        if not timer_seconds or timer_seconds <= 0:
            raise GameError("Invalid timer.")

        code = self._gen_code()
        rm = Room(code, host_sid, wrong_points, correct_points, timer_seconds)
        with self._mutex:
            self.rooms[code] = rm
        return rm

    def get_room(self, code):
        rm = self.rooms.get(str(code))
        if not rm:
            raise GameError("Room not found.")
        return rm

    def remove_room(self, code):
        with self._mutex:
            self.rooms.pop(str(code), None)

    def join_room(self, code, name, sid=None):
        rm = self.get_room(code)
        name = (name or "").strip()
        if not name:
            raise GameError("Name required.")

        with rm.lock:
            active = {p.name for p in rm.players.values()}
            rejoin = name in rm.departed

            if rm.status != STATUS_LOBBY and not rejoin:
                raise GameError("Game in progress.")

            if name in active:
                raise GameError("Name taken.")

            p = Player(str(uuid.uuid4())[:8], name, sid=sid)
            if rejoin:
                p.restore(rm.departed.pop(name))

            rm.players[p.id] = p

            if not rm.speaker_id:
                rm.speaker_id = p.id

            return p

    def leave_room(self, code, pid):
        rm = self.get_room(code)
        with rm.lock:
            p = rm.players.get(pid)
            if not p:
                return rm

            was_speaker = (rm.speaker_id == pid)

            if was_speaker and rm.running:
                p.time_spoken += rm._pause()

            rm.departed[p.name] = p.snapshot()
            del rm.players[pid]

            pause_needed = False

            if rm.pending_buzz == pid:
                rm.pending_buzz = rm.pending_speaker = None
                pause_needed = True

            if rm.awaiting_letter == pid:
                rm.awaiting_letter = None
                pause_needed = True

            if was_speaker:
                rm.speaker_id = next(iter(rm.players), None)
                pause_needed = True

            if pause_needed and rm.status in (STATUS_RUNNING, STATUS_AWAITING_DECISION, STATUS_AWAITING_LETTER):
                if rm.running:
                    rm._pause()
                rm.status = STATUS_PAUSED

            return rm

    def update_score(self, code, pid, delta):
        rm = self.get_room(code)
        with rm.lock:
            p = rm.players.get(pid)
            if not p:
                raise GameError("Player missing.")
            p.points += delta
            return rm

    def set_speaker(self, code, pid):
        rm = self.get_room(code)
        with rm.lock:
            if pid not in rm.players:
                raise GameError("Player missing.")
            rm.speaker_id = pid
            return rm

    def start_game(self, code):
        rm = self.get_room(code)
        with rm.lock:
            if rm.status != STATUS_LOBBY:
                raise GameError("Already started.")
            if not rm.players:
                raise GameError("Need players.")
            
            rm.speaker_id = rm.speaker_id or next(iter(rm.players))
            rm.remaining = rm.timer_total
            rm.status = STATUS_RUNNING
            rm._resume()
            return rm

    def handle_buzz(self, code, pid):
        rm = self.get_room(code)
        with rm.lock:
            if rm.status != STATUS_RUNNING:
                raise GameError("No active round.")
            if pid not in rm.players:
                raise GameError("Player missing.")
            if pid == rm.speaker_id:
                raise GameError("Can't self-buzz.")

            elapsed = rm._pause()
            if rm.speaker_id:
                rm.players[rm.speaker_id].time_spoken += elapsed

            rm.pending_buzz = pid
            rm.pending_speaker = rm.speaker_id
            rm.status = STATUS_AWAITING_DECISION
            return rm, elapsed

    def resolve_decision(self, code, is_correct):
        rm = self.get_room(code)
        with rm.lock:
            if rm.status != STATUS_AWAITING_DECISION or not rm.pending_buzz:
                raise GameError("No pending buzz.")

            buzzer = rm.players[rm.pending_buzz]

            if is_correct:
                buzzer.points += rm.correct_points
                buzzer.correct_jams += 1
                
                rm.awaiting_letter = rm.pending_speaker or buzzer.id
                rm.speaker_id = buzzer.id
                rm.pending_buzz = rm.pending_speaker = None
                rm.status = STATUS_AWAITING_LETTER
            else:
                buzzer.points += rm.wrong_points
                buzzer.wrong_jams += 1
                rm.pending_buzz = rm.pending_speaker = None
                rm.status = STATUS_PAUSED

            return rm

    def select_letter(self, code, letter=None, custom_text=None):
        rm = self.get_room(code)
        with rm.lock:
            if rm.status != STATUS_AWAITING_LETTER or not rm.awaiting_letter:
                raise GameError("No letter pending.")

            target = rm.players[rm.awaiting_letter]
            if letter:
                if letter not in FAULTS:
                    raise GameError("Invalid letter.")
                target.letter_tally[letter] += 1
            else:
                text = (custom_text or "").strip()
                if not text:
                    raise GameError("Text required.")
                target.others.append(text)

            rm.awaiting_letter = None
            rm.status = STATUS_PAUSED
            return rm

    def resume_round(self, code):
        rm = self.get_room(code)
        with rm.lock:
            if rm.status != STATUS_PAUSED:
                raise GameError("Not paused.")
            rm.status = STATUS_RUNNING
            rm._resume()
            return rm

    def reset_timer(self, code):
        rm = self.get_room(code)
        with rm.lock:
            if rm.running:
                raise GameError("Pause first.")
            
            for p in rm.players.values():
                p.reset_stats()
            
            rm.remaining = rm.timer_total
            return rm

    def check_expiry(self, code):
        rm = self.get_room(code)
        with rm.lock:
            if rm.status == STATUS_RUNNING and rm.get_remaining() <= 0:
                elapsed = rm._pause()
                if rm.speaker_id:
                    rm.players[rm.speaker_id].time_spoken += elapsed
                rm.status = STATUS_ENDED
                
                # win check
                if rm.players:
                    top_score = max(p.compute_score() for p in rm.players.values())
                    for p in rm.players.values():
                        if p.compute_score() == top_score:
                            p.games_won += 1
                            
                return True
            return False

    def get_winner(self, code):
        rm = self.get_room(code)
        if not rm.players:
            return None
        return max(rm.players.values(), key=lambda p: p.compute_score())

    def restart_game(self, code):
        rm = self.get_room(code)
        with rm.lock:
            for p in rm.players.values():
                p.roll_into_cumulative()
                p.reset_stats()

            rm.game_number += 1
            rm.departed = {}
            rm.remaining = rm.timer_total
            rm.running = False
            rm.running_since = None
            rm.pending_buzz = rm.pending_speaker = rm.awaiting_letter = None
            rm.status = STATUS_LOBBY
            rm.speaker_id = next(iter(rm.players), None)
            return rm

game_manager = GameManager()
