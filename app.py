from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room as sio_join_room
import os

from game_manager import (
    game_manager,
    GameError,
    STATUS_RUNNING,
    STATUS_ENDED,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key-change-this"

socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# sid -> {"room_code": str, "role": "host" | "player", "player_id": str (players only)}
sessions = {}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/host")
def host_page():
    return render_template("host.html")

@app.route("/play")
def player_page():
    return render_template("player.html")

@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")

@app.route("/service-worker.js")
def service_worker():
    response = send_from_directory("static", "service-worker.js")
    response.headers["Service-Worker-Allowed"] = "/"
    return response

def _require_host():
    sess = sessions.get(request.sid)
    if not sess or sess.get("role") != "host":
        emit("action_error", {"message": "Host-only action."})
        return None
    return sess["room_code"]

def _require_player():
    sess = sessions.get(request.sid)
    if not sess or sess.get("role") != "player":
        emit("action_error", {"message": "Player-only action."})
        return None, None
    return sess["room_code"], sess["player_id"]

def _broadcast_state(room_code):
    try:
        room = game_manager.get_room(room_code)
    except GameError:
        return
    socketio.emit("state_update", room.public_state(), room=room_code)

def _broadcast_game_ended(room_code):
    try:
        room = game_manager.get_room(room_code)
    except GameError:
        return
    winner = game_manager.get_winner(room_code)
    leaderboard = sorted(
        (p.to_result_dict() for p in room.players.values()),
        key=lambda p: p["score"],
        reverse=True,
    )
    socketio.emit(
        "game_ended",
        {
            "winner_name": winner.name if winner else None,
            "leaderboard": leaderboard,
        },
        room=room_code,
    )

def timer_loop(room_code):
    while True:
        socketio.sleep(0.1)

        try:
            room = game_manager.get_room(room_code)
        except GameError:
            break

        if room.status == STATUS_ENDED:
            break

        if room.status == STATUS_RUNNING:
            just_ended = game_manager.check_expiry(room_code)
            if just_ended:
                _broadcast_game_ended(room_code)
                break
            socketio.emit(
                "timer_update",
                {
                    "remaining": round(room.get_remaining(), 2),
                    "players": room.player_list(),
                },
                room=room_code,
            )

@socketio.on("connect")
def on_connect():
    pass

@socketio.on("disconnect")
def on_disconnect():
    sess = sessions.pop(request.sid, None)
    if not sess or sess.get("role") != "player":
        return

    code = sess["room_code"]
    try:
        game_manager.leave_room(code, sess["player_id"])
    except GameError:
        return
    _broadcast_state(code)

@socketio.on("create_room")
def on_create_room(data):
    try:
        wrong_points = float(data.get("wrong_points"))
        correct_points = float(data.get("correct_points"))
        timer_seconds = float(data.get("timer_seconds"))
    except (TypeError, ValueError):
        emit("action_error", {"message": "Settings must be numbers."})
        return

    try:
        room = game_manager.create_room(
            host_sid=request.sid,
            wrong_points=wrong_points,
            correct_points=correct_points,
            timer_seconds=timer_seconds,
        )
    except GameError as e:
        emit("action_error", {"message": str(e)})
        return

    sio_join_room(room.code)
    sessions[request.sid] = {"room_code": room.code, "role": "host"}
    emit("room_created", room.public_state())

@socketio.on("player_join")
def on_player_join(data):
    code = str(data.get("room_code", "")).strip()
    name = data.get("name", "")

    try:
        player = game_manager.join_room(code, name, sid=request.sid)
    except GameError as e:
        emit("join_error", {"message": str(e)})
        return

    sio_join_room(code)
    sessions[request.sid] = {
        "room_code": code,
        "role": "player",
        "player_id": player.id,
    }
    emit("join_success", {"player_id": player.id, "room_code": code})
    _broadcast_state(code)

@socketio.on("start_game")
def on_start_game(_data=None):
    code = _require_host()
    if code is None:
        return
    try:
        game_manager.start_game(code)
    except GameError as e:
        emit("action_error", {"message": str(e)})
        return
    _broadcast_state(code)
    socketio.start_background_task(timer_loop, code)

@socketio.on("resolve_decision")
def on_resolve_decision(data):
    code = _require_host()
    if code is None:
        return
    try:
        game_manager.resolve_decision(code, is_correct=bool(data.get("is_correct")))
    except GameError as e:
        emit("action_error", {"message": str(e)})
        return
    _broadcast_state(code)

@socketio.on("select_letter")
def on_select_letter(data):
    code = _require_host()
    if code is None:
        return
    try:
        game_manager.select_letter(
            code,
            letter=data.get("letter"),
            custom_text=data.get("custom_text"),
        )
    except GameError as e:
        emit("action_error", {"message": str(e)})
        return
    _broadcast_state(code)

@socketio.on("resume_round")
def on_resume_round(_data=None):
    code = _require_host()
    if code is None:
        return
    try:
        game_manager.resume_round(code)
    except GameError as e:
        emit("action_error", {"message": str(e)})
        return
    _broadcast_state(code)

@socketio.on("reset_timer")
def on_reset_timer(_data=None):
    code = _require_host()
    if code is None:
        return
    try:
        game_manager.reset_timer(code)
    except GameError as e:
        emit("action_error", {"message": str(e)})
        return
    _broadcast_state(code)

@socketio.on("update_score")
def on_update_score(data):
    code = _require_host()
    if code is None:
        return
    try:
        game_manager.update_score(code, data.get("player_id"), float(data.get("delta", 0)))
    except (GameError, TypeError, ValueError) as e:
        emit("action_error", {"message": str(e)})
        return
    _broadcast_state(code)

@socketio.on("set_speaker")
def on_set_speaker(data):
    code = _require_host()
    if code is None:
        return
    try:
        game_manager.set_speaker(code, data.get("player_id"))
    except GameError as e:
        emit("action_error", {"message": str(e)})
        return
    _broadcast_state(code)

@socketio.on("restart_game")
def on_restart_game(_data=None):
    code = _require_host()
    if code is None:
        return
    try:
        game_manager.restart_game(code)
    except GameError as e:
        emit("action_error", {"message": str(e)})
        return
    _broadcast_state(code)

@socketio.on("disband_room")
def on_disband_room(_data=None):
    code = _require_host()
    if code is None:
        return
    
    try:
        room = game_manager.get_room(code)
    except GameError:
        return
    
    overall_results = {}
    for p in room.players.values():
        overall_results[p.id] = p.to_cumulative_dict(include_current=True)

    socketio.emit("room_disbanded", {"overall_results": overall_results}, room=code)
    game_manager.remove_room(code)

@socketio.on("buzz")
def on_buzz(_data=None):
    code, player_id = _require_player()
    if code is None:
        return
    try:
        room, elapsed = game_manager.handle_buzz(code, player_id)
    except GameError as e:
        emit("action_error", {"message": str(e)})
        return

    socketio.emit(
        "buzzed",
        {
            "player_id": player_id,
            "player_name": room.players[player_id].name,
            "elapsed_credited": elapsed,
        },
        room=code,
    )
    _broadcast_state(code)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
