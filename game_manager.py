import random
import time
import uuid
from threading import Lock

LETTERS = ["Repetition", "Deviation", "SpeechDefect", "Grammar", "Gesticulation", "Qualification", "Pause", "LateStart"]

# Room lifecycle states
STATUS_LOBBY = "lobby"
STATUS_RUNNING = "running"
STATUS_AWAITING_DECISION = "awaiting_decision"
STATUS_AWAITING_LETTER = "awaiting_letter"
STATUS_PAUSED = "paused"
STATUS_ENDED = "ended"


class GameError(Exception):
    pass


class Player:
    def __init__(self, player_id, name, sid=None):
        self.id = player_id
        self.name = name
        self.sid = sid

        # Current game stats
        self.points = 0
        self.correct_jams = 0
        self.wrong_jams = 0
        self.time_spoken = 0.0
        self.letter_tally = {letter: 0 for letter in LETTERS}
        self.others = []
        
        # Cumulative/Overall stats across multiple games in the room
        self.games_played = 0
        self.games_won = 0  # <--- NEW TRACKER
        self.total_points = 0
        self.total_time_spoken = 0.0
        self.total_correct_jams = 0
        self.total_wrong_jams = 0
        self.total_letter_tally = {letter: 0 for letter in LETTERS}
        self.total_others = []

        self.joined_at = time.time()

    def reset_stats(self):
        """Clears stats for the *current* game only."""
        self.points = 0
        self.correct_jams = 0
        self.wrong_jams = 0
        self.time_spoken = 0.0
        self.letter_tally = {letter: 0 for letter in LETTERS}
        self.others = []
        
    def roll_into_cumulative(self):
        """Archives current game stats into the cumulative totals."""
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

    def restore(self, snapshot):
        self.points = snapshot["points"]
        self.time_spoken = snapshot["time_spoken"]
        self.correct_jams = snapshot["correct_jams"]
        self.wrong_jams = snapshot["wrong_jams"]
        self.letter_tally = dict(snapshot["letter_tally"])
        self.others = list(snapshot["others"])
        self.games_played = snapshot.get("games_played", 0)
        self.games_won = snapshot.get("games_won", 0)
        self.total_points = snapshot.get("total_points", 0)
        self.total_time_spoken = snapshot.get("total_time_spoken", 0.0)
        self.total_correct_jams = snapshot.get("total_correct_jams", 0)
        self.total_wrong_jams = snapshot.get("total_wrong_jams", 0)
        self.total_letter_tally = dict(snapshot.get("total_letter_tally", {l: 0 for l in LETTERS}))
        self.total_others = list(snapshot.get("total_others", []))

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
        """Returns the overall room lifetime stats for the player."""
        games = self.games_played + (1 if include_current else 0)
        pts = self.total_points + (self.points if include_current else 0)
        t_spoken = self.total_time_spoken + (self.time_spoken if include_current else 0)
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
            "score": round(pts + t_spoken, 2),
            "time_spoken": round(t_spoken, 2),
            "correct_jams": c_jams,
            "wrong_jams": w_jams,
            "letter_tally": tally,
            "others_count": len(others),
            "others": others,
        }


class Room:
    def __init__(self, code, host_sid, wrong_points, correct_points, timer_seconds):
        self.code = code
        self.host_sid = host_sid
        self.game_number = 1

        self.wrong_points = wrong_points
        self.correct_points = correct_points
        self.timer_total = float(timer_seconds)

        self.remaining = float(timer_seconds)
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
        if self.running and self.running_since is not None:
            elapsed = time.time() - self.running_since
            return max(0.0, self.remaining - elapsed)
        return max(0.0, self.remaining)

    def _pause(self):
        if self.running and self.running_since is not None:
            elapsed = time.time() - self.running_since
            elapsed = max(0.0, elapsed)
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
        live_player_id = None
        if self.running and self.running_since is not None:
            live_player_id = self.speaker_id
            live_extra = time.time() - self.running_since

        return [
            p.to_dict(self.speaker_id, live_extra if p.id == live_player_id else 0.0)
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
        self._rooms_lock = Lock()

    def _generate_code(self):
        with self._rooms_lock:
            for _ in range(1000):
                code = str(random.randint(100000, 999999))
                if code not in self.rooms:
                    return code
            raise GameError("Could not allocate a room code, try again.")

    def create_room(self, host_sid, wrong_points, correct_points, timer_seconds):
        if timer_seconds is None or timer_seconds <= 0:
            raise GameError("Timer must be a positive number of seconds.")

        code = self._generate_code()
        room = Room(code, host_sid, wrong_points, correct_points, timer_seconds)
        with self._rooms_lock:
            self.rooms[code] = room
        return room

    def get_room(self, code):
        room = self.rooms.get(str(code))
        if room is None:
            raise GameError("Room not found.")
        return room

    def remove_room(self, code):
        with self._rooms_lock:
            self.rooms.pop(str(code), None)

    def join_room(self, code, name, sid=None):
        room = self.get_room(code)
        name = (name or "").strip()
        if not name:
            raise GameError("Name cannot be empty.")

        with room.lock:
            active_names = {p.name for p in room.players.values()}
            is_rejoin = name in room.departed

            if room.status != STATUS_LOBBY and not is_rejoin:
                raise GameError("This game has already started.")

            if name in active_names:
                raise GameError("That name is already taken in this room.")

            player = Player(str(uuid.uuid4())[:8], name, sid=sid)
            if is_rejoin:
                player.restore(room.departed.pop(name))

            room.players[player.id] = player

            if room.speaker_id is None:
                room.speaker_id = player.id

            return player

    def leave_room(self, code, player_id):
        room = self.get_room(code)
        with room.lock:
            player = room.players.get(player_id)
            if player is None:
                return room

            was_speaker = (room.speaker_id == player_id)

            if was_speaker and room.running:
                elapsed = room._pause()
                player.time_spoken += elapsed

            room.departed[player.name] = player.snapshot()
            del room.players[player_id]

            needs_pause = False

            if room.pending_buzz == player_id:
                room.pending_buzz = None
                room.pending_speaker = None
                needs_pause = True

            if room.awaiting_letter == player_id:
                room.awaiting_letter = None
                needs_pause = True

            if was_speaker:
                room.speaker_id = next(iter(room.players), None)
                needs_pause = True

            if needs_pause and room.status in (STATUS_RUNNING, STATUS_AWAITING_DECISION, STATUS_AWAITING_LETTER):
                if room.running:
                    room._pause()
                room.status = STATUS_PAUSED

            return room

    def update_score(self, code, player_id, delta):
        room = self.get_room(code)
        with room.lock:
            player = room.players.get(player_id)
            if player is None:
                raise GameError("Player not found.")
            player.points += delta
            return room

    def set_speaker(self, code, player_id):
        room = self.get_room(code)
        with room.lock:
            if player_id not in room.players:
                raise GameError("Player not found.")
            room.speaker_id = player_id
            return room

    def start_game(self, code):
        room = self.get_room(code)
        with room.lock:
            if room.status != STATUS_LOBBY:
                raise GameError("Game already started.")
            if not room.players:
                raise GameError("Need at least one player to start.")
            if room.speaker_id is None:
                room.speaker_id = next(iter(room.players))

            room.remaining = room.timer_total
            room.status = STATUS_RUNNING
            room._resume()
            return room

    def handle_buzz(self, code, player_id):
        room = self.get_room(code)
        with room.lock:
            if room.status != STATUS_RUNNING:
                raise GameError("No active round to buzz on right now.")
            if player_id not in room.players:
                raise GameError("Player not found.")
            if player_id == room.speaker_id:
                raise GameError("The current speaker can't buzz on themselves.")

            elapsed = room._pause()
            if room.speaker_id is not None:
                room.players[room.speaker_id].time_spoken += elapsed

            room.pending_buzz = player_id
            room.pending_speaker = room.speaker_id
            room.status = STATUS_AWAITING_DECISION
            return room, elapsed

    def resolve_decision(self, code, is_correct):
        room = self.get_room(code)
        with room.lock:
            if room.status != STATUS_AWAITING_DECISION or room.pending_buzz is None:
                raise GameError("No buzz is currently awaiting a decision.")

            buzzer = room.players[room.pending_buzz]

            if is_correct:
                buzzer.points += room.correct_points
                buzzer.correct_jams += 1
                
                target_for_letter = room.pending_speaker if room.pending_speaker else buzzer.id
                
                room.speaker_id = buzzer.id
                room.awaiting_letter = target_for_letter
                room.pending_buzz = None
                room.pending_speaker = None
                room.status = STATUS_AWAITING_LETTER
            else:
                buzzer.points += room.wrong_points
                buzzer.wrong_jams += 1
                room.pending_buzz = None
                room.pending_speaker = None
                room.status = STATUS_PAUSED

            return room

    def select_letter(self, code, letter=None, custom_text=None):
        room = self.get_room(code)
        with room.lock:
            if room.status != STATUS_AWAITING_LETTER or room.awaiting_letter is None:
                raise GameError("No letter selection is pending.")

            target = room.players[room.awaiting_letter]
            if letter is not None:
                if letter not in LETTERS:
                    raise GameError("Invalid letter option.")
                target.letter_tally[letter] += 1
            else:
                text = (custom_text or "").strip()
                if not text:
                    raise GameError("Custom text cannot be empty.")
                target.others.append(text)

            room.awaiting_letter = None
            room.status = STATUS_PAUSED
            return room

    def resume_round(self, code):
        room = self.get_room(code)
        with room.lock:
            if room.status != STATUS_PAUSED:
                raise GameError("Round isn't paused, nothing to resume.")
            room.status = STATUS_RUNNING
            room._resume()
            return room

    def reset_timer(self, code):
        room = self.get_room(code)
        with room.lock:
            if room.running:
                raise GameError("Pause the round before resetting the timer.")
            
            for player in room.players.values():
                player.reset_stats()
            
            room.remaining = room.timer_total
            return room

    def check_expiry(self, code):
        room = self.get_room(code)
        with room.lock:
            if room.status == STATUS_RUNNING and room.get_remaining() <= 0:
                elapsed = room._pause()
                if room.speaker_id is not None:
                    room.players[room.speaker_id].time_spoken += elapsed
                room.status = STATUS_ENDED
                
                # Check for the winner(s) and increment their games_won tracker
                if room.players:
                    max_score = max(p.compute_score() for p in room.players.values())
                    for p in room.players.values():
                        if p.compute_score() == max_score:
                            p.games_won += 1
                            
                return True
            return False

    def get_winner(self, code):
        room = self.get_room(code)
        if not room.players:
            return None
        return max(room.players.values(), key=lambda p: p.compute_score())

    def restart_game(self, code):
        room = self.get_room(code)
        with room.lock:
            for player in room.players.values():
                player.roll_into_cumulative()
                player.reset_stats()

            room.game_number += 1
            room.departed = {}
            room.remaining = room.timer_total
            room.running = False
            room.running_since = None
            room.pending_buzz = None
            room.pending_speaker = None
            room.awaiting_letter = None
            room.status = STATUS_LOBBY
            room.speaker_id = next(iter(room.players), None)
            return room

game_manager = GameManager()