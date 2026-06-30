from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room as join_sio_room
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

conns = {}

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/host")
def host_view():
    return render_template("host.html")

@app.route("/play")
def player_view():
    return render_template("player.html")

@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")

@app.route("/service-worker.js")
def sw():
    res = send_from_directory("static", "service-worker.js")
    res.headers["Service-Worker-Allowed"] = "/"
    return res

# auth host
def get_host():
    user = conns.get(request.sid)
    if not user or user.get("role") != "host":
        emit("action_error", {"message": "Host-only action."})
        return None
    return user["room_code"]

# auth player
def get_player():
    user = conns.get(request.sid)
    if not user or user.get("role") != "player":
        emit("action_error", {"message": "Player-only action."})
        return None, None
    return user["room_code"], user["player_id"]

# sync room
def sync_room(code):
    try:
        room = game_manager.get_room(code)
    except GameError:
        return
    socketio.emit("state_update", room.public_state(), room=code)

def finish_game(code):
    try:
        room = game_manager.get_room(code)
    except GameError:
        return
    winner = game_manager.get_winner(code)
    board = sorted(
        (p.to_result_dict() for p in room.players.values()),
        key=lambda p: p["score"],
        reverse=True,
    )
    socketio.emit(
        "game_ended",
        {
            "winner_name": winner.name if winner else None,
            "leaderboard": board,
        },
        room=code,
    )

# clock loop
def run_clock(code):
    while True:
        socketio.sleep(0.1)

        try:
            room = game_manager.get_room(code)
        except GameError:
            break

        if room.status == STATUS_ENDED:
            break

        if room.status == STATUS_RUNNING:
            done = game_manager.check_expiry(code)
            if done:
                sync_room(code)
                finish_game(code)
                break
            socketio.emit(
                "timer_update",
                {
                    "remaining": round(room.get_remaining(), 2),
                    "players": room.player_list(),
                },
                room=code,
            )

@socketio.on("connect")
def on_connect():
    pass

@socketio.on("disconnect")
def on_disconnect():
    user = conns.pop(request.sid, None)
    if not user or user.get("role") != "player":
        return

    code = user["room_code"]
    try:
        game_manager.leave_room(code, user["player_id"])
    except GameError:
        return
    sync_room(code)

@socketio.on("create_room")
def create_room(req):
    try:
        wrong_pts = float(req.get("wrong_points"))
        correct_pts = float(req.get("correct_points"))
        timer_secs = float(req.get("timer_seconds"))
    except (TypeError, ValueError):
        emit("action_error", {"message": "Settings must be numbers."})
        return

    try:
        room = game_manager.create_room(
            host_sid=request.sid,
            wrong_points=wrong_pts,
            correct_points=correct_pts,
            timer_seconds=timer_secs,
        )
    except GameError as err:
        emit("action_error", {"message": str(err)})
        return

    join_sio_room(room.code)
    conns[request.sid] = {"room_code": room.code, "role": "host"}
    emit("room_created", room.public_state())

@socketio.on("player_join")
def join_game(req):
    code = str(req.get("room_code", "")).strip()
    name = req.get("name", "")

    try:
        player = game_manager.join_room(code, name, sid=request.sid)
    except GameError as err:
        emit("join_error", {"message": str(err)})
        return

    join_sio_room(code)
    conns[request.sid] = {
        "room_code": code,
        "role": "player",
        "player_id": player.id,
    }
    emit("join_success", {"player_id": player.id, "room_code": code})
    sync_room(code)

@socketio.on("start_game")
def start_game(req=None):
    code = get_host()
    if not code:
        return
    try:
        game_manager.start_game(code)
    except GameError as err:
        emit("action_error", {"message": str(err)})
        return
    sync_room(code)
    socketio.start_background_task(run_clock, code)

@socketio.on("resolve_decision")
def resolve_decision(req):
    code = get_host()
    if not code:
        return
    try:
        game_manager.resolve_decision(code, is_correct=bool(req.get("is_correct")))
    except GameError as err:
        emit("action_error", {"message": str(err)})
        return
    sync_room(code)

@socketio.on("select_letter")
def select_letter(req):
    code = get_host()
    if not code:
        return
    try:
        game_manager.select_letter(
            code,
            letter=req.get("letter"),
            custom_text=req.get("custom_text"),
        )
    except GameError as err:
        emit("action_error", {"message": str(err)})
        return
    sync_room(code)

@socketio.on("resume_round")
def resume_round(req=None):
    code = get_host()
    if not code:
        return
    try:
        game_manager.resume_round(code)
    except GameError as err:
        emit("action_error", {"message": str(err)})
        return
    sync_room(code)

@socketio.on("reset_timer")
def reset_timer(req=None):
    code = get_host()
    if not code:
        return
    try:
        game_manager.reset_timer(code)
    except GameError as err:
        emit("action_error", {"message": str(err)})
        return
    sync_room(code)

@socketio.on("update_score")
def update_score(req):
    code = get_host()
    if not code:
        return
    try:
        game_manager.update_score(code, req.get("player_id"), float(req.get("delta", 0)))
    except (GameError, TypeError, ValueError) as err:
        emit("action_error", {"message": str(err)})
        return
    sync_room(code)

@socketio.on("set_speaker")
def set_speaker(req):
    code = get_host()
    if not code:
        return
    try:
        game_manager.set_speaker(code, req.get("player_id"))
    except GameError as err:
        emit("action_error", {"message": str(err)})
        return
    sync_room(code)

@socketio.on("restart_game")
def restart_game(req=None):
    code = get_host()
    if not code:
        return
    try:
        game_manager.restart_game(code)
    except GameError as err:
        emit("action_error", {"message": str(err)})
        return
    sync_room(code)

@socketio.on("disband_room")
def disband_room(req=None):
    code = get_host()
    if not code:
        return
    
    try:
        room = game_manager.get_room(code)
    except GameError:
        return
    
    results = {}
    for p in room.players.values():
        results[p.id] = p.to_cumulative_dict(include_current=True)

    socketio.emit("room_disbanded", {"overall_results": results}, room=code)
    game_manager.remove_room(code)

@socketio.on("buzz")
def handle_buzz(req=None):
    code, pid = get_player()
    if not code:
        return
    try:
        room, elapsed = game_manager.handle_buzz(code, pid)
    except GameError as err:
        emit("action_error", {"message": str(err)})
        return

    socketio.emit(
        "buzzed",
        {
            "player_id": pid,
            "player_name": room.players[pid].name,
            "elapsed_credited": elapsed,
        },
        room=code,
    )
    sync_room(code)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
