(() => {
  const socket = io();

  // dom hooks
  const viewSetup = document.getElementById("view-setup");
  const viewRoom = document.getElementById("view-room");
  const setupForm = document.getElementById("setup-form");
  const wrongPointsInput = document.getElementById("wrong-points");
  const correctPointsInput = document.getElementById("correct-points");
  const timerSecondsInput = document.getElementById("timer-seconds");
  const setupError = document.getElementById("setup-error");
  const roomCodeDisplay = document.getElementById("room-code-display");
  const gameNumberHost = document.getElementById("game-number-host");
  const timerDisplay = document.getElementById("timer-display");
  const resetTimerBtn = document.getElementById("reset-timer-btn");
  const disbandBtn = document.getElementById("disband-btn");
  const statusLine = document.getElementById("status-line");
  const startBtn = document.getElementById("start-btn");
  const resumeBtn = document.getElementById("resume-btn");
  const restartBtn = document.getElementById("restart-btn");
  const playerListEl = document.getElementById("player-list");
  const playerDialog = document.getElementById("player-dialog");
  const playerDialogClose = document.getElementById("player-dialog-close");
  const playerDialogName = document.getElementById("player-dialog-name");
  const playerDialogScore = document.getElementById("player-dialog-score");
  const playerScoreMinus = document.getElementById("player-score-minus");
  const playerScorePlus = document.getElementById("player-score-plus");
  const playerSetSpeaker = document.getElementById("player-set-speaker");
  const decisionDialog = document.getElementById("decision-dialog");
  const decisionDialogTitle = document.getElementById("decision-dialog-title");
  const decisionWrongBtn = document.getElementById("decision-wrong-btn");
  const decisionCorrectBtn = document.getElementById("decision-correct-btn");
  const letterDialog = document.getElementById("letter-dialog");
  const letterGrid = document.getElementById("letter-grid");
  const letterOtherRow = document.getElementById("letter-other-row");
  const letterOtherInput = document.getElementById("letter-other-input");
  const letterOtherSubmit = document.getElementById("letter-other-submit");
  const endedDialog = document.getElementById("ended-dialog");
  const endedWinnerText = document.getElementById("ended-winner-text");
  const endedCloseBtn = document.getElementById("ended-close-btn");
  const hostDisbandedDialog = document.getElementById("host-disbanded-dialog");
  const hostTotalGames = document.getElementById("host-total-games");
  const hostOverallTbody = document.getElementById("host-overall-tbody");
  const buzzSound = new Audio('/static/sounds/buzz.mp3');

  const FAULTS = ["Repetition", "Deviation", "SpeechDefect", "Grammar", "Gesticulation", "Qualification", "Pause", "LateStart"];

  let state = null;
  let activePlayerId = null;

  // utils
  const toTime = n => Number(n).toFixed(2);
  const toScore = n => Number(n).toFixed(2);
  const getPlayer = (st, id) => st?.players.find(p => p.id === id) || null;

  const getStatusMsg = st => {
    if (st === "lobby") return "Waiting to start...";
    if (st === "paused") return "Round paused.";
    if (st === "ended") return "Game ended.";
    return "";
  };

  function syncPlayers(st) {
    playerListEl.innerHTML = "";
    playerListEl.classList.add("clickable");
    
    st.players.forEach(p => {
      const li = document.createElement("li");
      li.dataset.playerId = p.id;
      if (p.is_speaker) li.classList.add("is-speaker");

      const nameSpan = document.createElement("span");
      nameSpan.className = "player-name";
      nameSpan.textContent = p.name;
      
      if (p.is_speaker) {
        const tag = document.createElement("span");
        tag.className = "speaker-tag";
        tag.textContent = "Speaking";
        nameSpan.append(tag);
      }

      const scoreSpan = document.createElement("span");
      scoreSpan.className = "player-score";
      scoreSpan.textContent = toScore(p.score);

      li.append(nameSpan, scoreSpan);
      li.onclick = () => openPlayer(p.id);

      playerListEl.append(li);
    });
  }

  function syncRoom(st) {
    state = st;

    roomCodeDisplay.textContent = st.room_code;
    gameNumberHost.textContent = "Game " + st.game_number;
    timerDisplay.textContent = toTime(st.remaining);
    statusLine.textContent = getStatusMsg(st.status);
    resetTimerBtn.disabled = st.running;

    startBtn.hidden = st.status !== "lobby";
    resumeBtn.hidden = st.status !== "paused";
    restartBtn.hidden = st.status !== "ended";

    syncPlayers(st);

    // buzz check
    if (st.status === "awaiting_decision" && st.pending_buzz) {
      const buzzer = getPlayer(st, st.pending_buzz);
      decisionDialogTitle.textContent = buzzer ? `${buzzer.name} buzzed! Wrong or correct jam?` : "Buzz received";
      decisionDialog.hidden = false;
    } else {
      decisionDialog.hidden = true;
    }

    // letter check
    if (st.status === "awaiting_letter" && st.awaiting_letter) {
      letterOtherInput.value = "";
      letterOtherRow.hidden = true;
      letterDialog.hidden = false;
    } else {
      letterDialog.hidden = true;
    }

    if (st.status !== "ended") endedDialog.hidden = true;

    // live score update if modal is open
    if (activePlayerId && !playerDialog.hidden) {
      const p = getPlayer(st, activePlayerId);
      if (p) {
        playerDialogScore.textContent = toScore(p.score);
      } else {
        closePlayer();
      }
    }
  }

  function setupGrid() {
    letterGrid.innerHTML = "";
    FAULTS.forEach(f => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = f;
      btn.onclick = () => socket.emit("select_letter", { letter: f });
      letterGrid.append(btn);
    });

    const btnOther = document.createElement("button");
    btnOther.type = "button";
    btnOther.textContent = "Others";
    btnOther.onclick = () => {
      letterOtherRow.hidden = false;
      letterOtherInput.focus();
    };
    letterGrid.append(btnOther);
  }

  function openPlayer(pid) {
    const p = getPlayer(state, pid);
    if (!p) return;
    activePlayerId = pid;
    playerDialogName.textContent = p.name;
    playerDialogScore.textContent = toScore(p.score);
    playerDialog.hidden = false;
  }

  function closePlayer() {
    playerDialog.hidden = true;
    activePlayerId = null;
  }

  // dom events
  playerDialogClose.onclick = closePlayer;

  playerScorePlus.onclick = () => {
    if (activePlayerId) socket.emit("update_score", { player_id: activePlayerId, delta: 1 });
  };

  playerScoreMinus.onclick = () => {
    if (activePlayerId) socket.emit("update_score", { player_id: activePlayerId, delta: -1 });
  };

  playerSetSpeaker.onclick = () => {
    if (activePlayerId) socket.emit("set_speaker", { player_id: activePlayerId });
  };

  setupForm.onsubmit = e => {
    e.preventDefault();
    setupError.hidden = true;
    socket.emit("create_room", {
      wrong_points: wrongPointsInput.value,
      correct_points: correctPointsInput.value,
      timer_seconds: timerSecondsInput.value,
    });
  };

  startBtn.onclick = () => socket.emit("start_game");
  resumeBtn.onclick = () => socket.emit("resume_round");
  restartBtn.onclick = () => socket.emit("restart_game");

  resetTimerBtn.onclick = () => {
    if (confirm("Reset timer and wipe all scores for THIS match?")) socket.emit("reset_timer");
  };

  disbandBtn.onclick = () => {
    if (confirm("Disband this room? This can't be undone.")) socket.emit("disband_room");
  };

  decisionWrongBtn.onclick = () => socket.emit("resolve_decision", { is_correct: false });
  decisionCorrectBtn.onclick = () => socket.emit("resolve_decision", { is_correct: true });

  letterOtherSubmit.onclick = () => {
    const val = letterOtherInput.value.trim();
    if (val) socket.emit("select_letter", { custom_text: val });
  };

  endedCloseBtn.onclick = () => { endedDialog.hidden = true; };

  // socket events
  socket.on("room_created", st => {
    viewSetup.hidden = true;
    viewRoom.hidden = false;
    syncRoom(st);
  });

  socket.on("state_update", syncRoom);

  socket.on("timer_update", data => {
    timerDisplay.textContent = toTime(data.remaining);
    if (state) {
      state.remaining = data.remaining;
      if (data.players) {
        state.players = data.players;
        syncPlayers(state);
        
        if (activePlayerId && !playerDialog.hidden) {
          const p = getPlayer(state, activePlayerId);
          if (p) playerDialogScore.textContent = toScore(p.score);
        }
      }
    }
  });

  socket.on("buzzed", () => {
    buzzSound.currentTime = 0; 
    buzzSound.play().catch(() => {});
  });

  socket.on("game_ended", data => {
    endedWinnerText.textContent = data.winner_name ? `${data.winner_name} is the winner!` : "Game ended - no players to rank.";
    endedDialog.hidden = false;
  });

  socket.on("room_disbanded", data => {
    if (data?.overall_results) {
      const players = Object.values(data.overall_results);
      
      let maxGames = 0;
      players.forEach(p => { if (p.games_played > maxGames) maxGames = p.games_played; });
      hostTotalGames.textContent = maxGames;

      players.sort((a, b) => b.score - a.score);

      hostOverallTbody.innerHTML = "";
      players.forEach(p => {
        const tr = document.createElement("tr");
        
        const tdName = document.createElement("td");
        tdName.textContent = p.name;
        tdName.style.textAlign = "left";
        
        const tdWins = document.createElement("td");
        tdWins.textContent = p.games_won;
        tdWins.style.textAlign = "center";
        
        const tdScore = document.createElement("td");
        tdScore.textContent = toScore(p.score);
        tdScore.style.textAlign = "right";
        tdScore.style.fontWeight = "bold";
        
        tr.append(tdName, tdWins, tdScore);
        hostOverallTbody.append(tr);
      });
      
      hostDisbandedDialog.hidden = false;
    } else {
      location.href = "/";
    }
  });

  socket.on("action_error", data => {
    if (viewSetup.hidden) {
      alert(data.message);
    } else {
      setupError.textContent = data.message;
      setupError.hidden = false;
    }
  });

  // init
  setupGrid();
})();
