(function () {
  "use strict";

  const socket = io();

  // ---- DOM references ----
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

  // New Host Disband Dialog elements
  const hostDisbandedDialog = document.getElementById("host-disbanded-dialog");
  const hostTotalGames = document.getElementById("host-total-games");
  const hostOverallTbody = document.getElementById("host-overall-tbody");

 const LETTERS = ["Repetition", "Deviation", "SpeechDefect", "Grammar", "Gesticulation", "Qualification", "Pause", "LateStart"];

  let currentState = null;
  let selectedPlayerId = null;

  function fmtTime(seconds) { return Number(seconds).toFixed(2); }
  function fmtScore(score) { return Number(score).toFixed(2); }

  function findPlayer(state, playerId) {
    if (!state) return null;
    return state.players.find((p) => p.id === playerId) || null;
  }

  function statusMessage(state) {
    switch (state.status) {
      case "lobby": return `Waiting to start - ${state.players.length} player(s) joined.`;
      case "running": return "Round in progress.";
      case "awaiting_decision": return "Waiting for your decision...";
      case "awaiting_letter": return "Pick the reason for the jam.";
      case "paused": return "Round paused - adjust speaker/points, then resume.";
      case "ended": return "Game ended.";
      default: return "";
    }
  }

  function renderPlayerList(state) {
    playerListEl.innerHTML = "";
    playerListEl.classList.add("clickable");
    state.players.forEach((player) => {
      const li = document.createElement("li");
      li.dataset.playerId = player.id;
      if (player.is_speaker) li.classList.add("is-speaker");

      const nameSpan = document.createElement("span");
      nameSpan.className = "player-name";
      nameSpan.textContent = player.name;
      if (player.is_speaker) {
        const tag = document.createElement("span");
        tag.className = "speaker-tag";
        tag.textContent = "Speaking";
        nameSpan.appendChild(tag);
      }

      const scoreSpan = document.createElement("span");
      scoreSpan.className = "player-score";
      scoreSpan.textContent = fmtScore(player.score);

      li.appendChild(nameSpan);
      li.appendChild(scoreSpan);
      li.addEventListener("click", () => openPlayerDialog(player.id));

      playerListEl.appendChild(li);
    });
  }

  function renderRoomState(state) {
    currentState = state;

    roomCodeDisplay.textContent = state.room_code;
    gameNumberHost.textContent = "Game " + state.game_number;
    timerDisplay.textContent = fmtTime(state.remaining);
    statusLine.textContent = statusMessage(state);
    resetTimerBtn.disabled = state.running;

    startBtn.hidden = state.status !== "lobby";
    resumeBtn.hidden = state.status !== "paused";
    restartBtn.hidden = state.status !== "ended";

    renderPlayerList(state);

    if (state.status === "awaiting_decision" && state.pending_buzz) {
      const buzzer = findPlayer(state, state.pending_buzz);
      decisionDialogTitle.textContent = buzzer
        ? `${buzzer.name} buzzed! Wrong or correct jam?`
        : "Buzz received";
      decisionDialog.hidden = false;
    } else {
      decisionDialog.hidden = true;
    }

    if (state.status === "awaiting_letter" && state.awaiting_letter) {
      letterOtherInput.value = "";
      letterOtherRow.hidden = true;
      letterDialog.hidden = false;
    } else {
      letterDialog.hidden = true;
    }

    if (state.status !== "ended") {
      endedDialog.hidden = true;
    }

    if (selectedPlayerId && !playerDialog.hidden) {
      const p = findPlayer(state, selectedPlayerId);
      if (p) {
        playerDialogScore.textContent = fmtScore(p.score);
      } else {
        closePlayerDialog();
      }
    }
  }

  function buildLetterGrid() {
    letterGrid.innerHTML = "";
    LETTERS.forEach((letter) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = letter;
      btn.addEventListener("click", () => {
        socket.emit("select_letter", { letter: letter });
      });
      letterGrid.appendChild(btn);
    });

    const othersBtn = document.createElement("button");
    othersBtn.type = "button";
    othersBtn.textContent = "Others";
    othersBtn.addEventListener("click", () => {
      letterOtherRow.hidden = false;
      letterOtherInput.focus();
    });
    letterGrid.appendChild(othersBtn);
  }

  function openPlayerDialog(playerId) {
    const player = findPlayer(currentState, playerId);
    if (!player) return;
    selectedPlayerId = playerId;
    playerDialogName.textContent = player.name;
    playerDialogScore.textContent = fmtScore(player.score);
    playerDialog.hidden = false;
  }

  function closePlayerDialog() {
    playerDialog.hidden = true;
    selectedPlayerId = null;
  }

  playerDialogClose.addEventListener("click", closePlayerDialog);

  playerScorePlus.addEventListener("click", () => {
    if (!selectedPlayerId) return;
    socket.emit("update_score", { player_id: selectedPlayerId, delta: 1 });
  });

  playerScoreMinus.addEventListener("click", () => {
    if (!selectedPlayerId) return;
    socket.emit("update_score", { player_id: selectedPlayerId, delta: -1 });
  });

  playerSetSpeaker.addEventListener("click", () => {
    if (!selectedPlayerId) return;
    socket.emit("set_speaker", { player_id: selectedPlayerId });
  });

  setupForm.addEventListener("submit", (e) => {
    e.preventDefault();
    setupError.hidden = true;
    socket.emit("create_room", {
      wrong_points: wrongPointsInput.value,
      correct_points: correctPointsInput.value,
      timer_seconds: timerSecondsInput.value,
    });
  });

  startBtn.addEventListener("click", () => socket.emit("start_game"));
  resumeBtn.addEventListener("click", () => socket.emit("resume_round"));
  restartBtn.addEventListener("click", () => socket.emit("restart_game"));

  resetTimerBtn.addEventListener("click", () => {
    if (window.confirm("Reset timer and wipe all scores for THIS match?")) {
      socket.emit("reset_timer");
    }
  });

  disbandBtn.addEventListener("click", () => {
    if (window.confirm("Disband this room? This can't be undone.")) {
      socket.emit("disband_room");
    }
  });

  decisionWrongBtn.addEventListener("click", () => {
    socket.emit("resolve_decision", { is_correct: false });
  });

  decisionCorrectBtn.addEventListener("click", () => {
    socket.emit("resolve_decision", { is_correct: true });
  });

  letterOtherSubmit.addEventListener("click", () => {
    const text = letterOtherInput.value.trim();
    if (!text) return;
    socket.emit("select_letter", { custom_text: text });
  });

  endedCloseBtn.addEventListener("click", () => {
    endedDialog.hidden = true;
  });

  socket.on("room_created", (state) => {
    viewSetup.hidden = true;
    viewRoom.hidden = false;
    renderRoomState(state);
  });

  socket.on("state_update", (state) => {
    renderRoomState(state);
  });

  socket.on("timer_update", (data) => {
    timerDisplay.textContent = fmtTime(data.remaining);
    if (currentState) {
      currentState.remaining = data.remaining;
      if (data.players) {
        currentState.players = data.players;
        renderPlayerList(currentState);
        if (selectedPlayerId && !playerDialog.hidden) {
          const p = findPlayer(currentState, selectedPlayerId);
          if (p) playerDialogScore.textContent = fmtScore(p.score);
        }
      }
    }
  });

  socket.on("game_ended", (data) => {
    endedWinnerText.textContent = data.winner_name
      ? `${data.winner_name} is the winner!`
      : "Game ended - no players to rank.";
    endedDialog.hidden = false;
  });

  // Replaced direct redirect with summary logic
  socket.on("room_disbanded", (data) => {
    if (data && data.overall_results) {
      const players = Object.values(data.overall_results);
      
      // Calculate total games played based on the highest games_played value
      let maxGames = 0;
      players.forEach(p => {
        if (p.games_played > maxGames) maxGames = p.games_played;
      });
      hostTotalGames.textContent = maxGames;

      // Sort the players by highest score
      players.sort((a, b) => b.score - a.score);

      // Build the table rows
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
        tdScore.textContent = fmtScore(p.score);
        tdScore.style.textAlign = "right";
        tdScore.style.fontWeight = "bold";
        
        tr.appendChild(tdName);
        tr.appendChild(tdWins);
        tr.appendChild(tdScore);
        hostOverallTbody.appendChild(tr);
      });
      
      // Show the summary dialog instead of redirecting
      hostDisbandedDialog.hidden = false;
    } else {
      // Fallback if the room was empty
      window.location.href = "/";
    }
  });

  socket.on("action_error", (data) => {
    if (viewSetup.hidden) {
      window.alert(data.message);
    } else {
      setupError.textContent = data.message;
      setupError.hidden = false;
    }
  });

  buildLetterGrid();
})();