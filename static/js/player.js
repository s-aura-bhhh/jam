(function () {
  "use strict";

  const socket = io();

  let myPlayerId = null;
  let myRoomCode = null;
  let myResult = null; 

  const viewJoin     = document.getElementById("view-join");
  const viewWaiting  = document.getElementById("view-waiting");
  const viewGame     = document.getElementById("view-game");
  const viewResults  = document.getElementById("view-results");

  const joinForm      = document.getElementById("join-form");
  const joinRoomCode  = document.getElementById("join-room-code");
  const joinName      = document.getElementById("join-name");
  const joinError     = document.getElementById("join-error");

  const waitingRoomCode   = document.getElementById("waiting-room-code");
  const waitingPlayerList = document.getElementById("waiting-player-list");

  const gameNumberDisplay = document.getElementById("game-number-display");
  const gameTimer         = document.getElementById("game-timer");
  const speakerBanner     = document.getElementById("speaker-banner");
  const buzzBtn           = document.getElementById("buzz-btn");
  const gameStatusLine    = document.getElementById("game-status-line");
  const gamePlayerList    = document.getElementById("game-player-list");

  const resultScore   = document.getElementById("result-score");
  const resultTime    = document.getElementById("result-time");
  const resultCorrect = document.getElementById("result-correct");
  const resultWrong   = document.getElementById("result-wrong");
  const resultLetters = document.getElementById("result-letters");

  const endedDialog     = document.getElementById("ended-dialog");
  const endedWinnerText = document.getElementById("ended-winner-text");
  const endedCloseBtn   = document.getElementById("ended-close-btn");
  const disbandedDialog = document.getElementById("disbanded-dialog");

  function showOnly(sectionEl) {
    [viewJoin, viewWaiting, viewGame, viewResults].forEach((v) => {
      v.hidden = v !== sectionEl;
    });
  }

  function fmtTime(seconds) { return Number(seconds).toFixed(2); }
  function fmtScore(score) { return Number(score).toFixed(2); }

  function renderPlayerList(listEl, players) {
    listEl.innerHTML = "";
    players.forEach((p) => {
      const li = document.createElement("li");
      if (p.is_speaker) li.classList.add("is-speaker");
      if (p.id === myPlayerId) li.classList.add("is-me");

      const nameSpan = document.createElement("span");
      nameSpan.className = "player-name";
      nameSpan.textContent = p.name;

      if (p.is_speaker) {
        const tag = document.createElement("span");
        tag.className = "speaker-tag";
        tag.textContent = "Speaking";
        nameSpan.appendChild(tag);
      }
      if (p.id === myPlayerId) {
        const tag = document.createElement("span");
        tag.className = "me-tag";
        tag.textContent = "You";
        nameSpan.appendChild(tag);
      }

      const scoreSpan = document.createElement("span");
      scoreSpan.className = "player-score";
      scoreSpan.textContent = fmtScore(p.score);

      li.appendChild(nameSpan);
      li.appendChild(scoreSpan);
      listEl.appendChild(li);
    });
  }

  function statusMessage(state) {
    switch (state.status) {
      case "running": return "";
      case "awaiting_decision": return "Buzz received — waiting for host decision…";
      case "awaiting_letter": return "Correct jam! Host is selecting the mistake type…";
      case "paused": return "Round paused — host will resume shortly.";
      case "ended": return "Game over!";
      default: return "";
    }
  }

  function updateBuzzBtn(state) {
    const isSpeaker = state.speaker_id === myPlayerId;
    const canBuzz = state.status === "running" && !isSpeaker;
    buzzBtn.disabled = !canBuzz;

    if (isSpeaker) {
      buzzBtn.textContent = "YOU'RE SPEAKING";
    } else {
      buzzBtn.textContent = "BUZZ";
    }
  }

  function updateSpeakerBanner(state) {
    if (!state.speaker_id) {
      speakerBanner.textContent = "";
      return;
    }
    const speaker = state.players.find((p) => p.id === state.speaker_id);
    if (speaker) {
      speakerBanner.textContent =
        speaker.id === myPlayerId ? "🎤 You are speaking" : `🎤 ${speaker.name} is speaking`;
    }
  }

  joinForm.addEventListener("submit", (e) => {
    e.preventDefault();
    joinError.hidden = true;
    const code = joinRoomCode.value.trim();
    const name = joinName.value.trim();
    if (!code || !name) return;
    socket.emit("player_join", { room_code: code, name });
  });

  buzzBtn.addEventListener("click", () => socket.emit("buzz"));

  endedCloseBtn.addEventListener("click", () => {
    endedDialog.hidden = true;
    if (myResult) {
      renderResults(myResult);
      showOnly(viewResults);
    }
  });

  function renderResults(playerData) {
    resultScore.textContent   = fmtScore(playerData.score);
    resultTime.textContent    = playerData.time_spoken;
    resultCorrect.textContent = playerData.correct_jams;
    resultWrong.textContent   = playerData.wrong_jams;

    resultLetters.innerHTML = "";
    const letters = Object.entries(playerData.letter_tally || {});
    letters.forEach(([letter, count]) => {
      if (count === 0) return;
      const tr = document.createElement("tr");
      const th = document.createElement("th"); th.textContent = letter;
      const td = document.createElement("td"); td.textContent = count;
      tr.appendChild(th); tr.appendChild(td);
      resultLetters.appendChild(tr);
    });

    if (playerData.others_count > 0) {
      const tr = document.createElement("tr");
      const th = document.createElement("th"); th.textContent = "Other";
      const td = document.createElement("td"); td.textContent = playerData.others_count;
      tr.appendChild(th); tr.appendChild(td);
      resultLetters.appendChild(tr);

      if (playerData.others && playerData.others.length) {
        const tr2 = document.createElement("tr");
        const td2 = document.createElement("td");
        td2.colSpan = 2;
        td2.style.fontSize = "0.8rem";
        td2.style.color = "var(--color-text-muted)";
        td2.textContent = playerData.others.join(", ");
        tr2.appendChild(td2);
        resultLetters.appendChild(tr2);
      }
    }

    if (resultLetters.rows.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 2;
      td.style.color = "var(--color-text-muted)";
      td.textContent = "No mistakes recorded.";
      tr.appendChild(td);
      resultLetters.appendChild(tr);
    }
  }

  socket.on("join_success", (data) => {
    myPlayerId = data.player_id;
    myRoomCode = data.room_code;
    waitingRoomCode.textContent = data.room_code;
    showOnly(viewWaiting);
  });

  socket.on("join_error", (data) => {
    joinError.textContent = data.message;
    joinError.hidden = false;
  });

  socket.on("state_update", (state) => {
    if (state.status === "lobby") {
      waitingRoomCode.textContent = state.room_code;
      renderPlayerList(waitingPlayerList, state.players);
      showOnly(viewWaiting);
      return;
    }

    if (!(state.status === "ended" && !viewResults.hidden)) {
      showOnly(viewGame);
    }
    gameNumberDisplay.textContent = "Game " + state.game_number;
    gameTimer.textContent = fmtTime(state.remaining);
    gameStatusLine.textContent = statusMessage(state);
    updateSpeakerBanner(state);
    updateBuzzBtn(state);
    renderPlayerList(gamePlayerList, state.players);
  });

  socket.on("timer_update", (data) => {
    gameTimer.textContent = fmtTime(data.remaining);
    if (data.players) renderPlayerList(gamePlayerList, data.players);
  });

  socket.on("buzzed", (data) => {
    if (data.player_id === myPlayerId) {
      gameStatusLine.textContent = "Your buzz was received! Waiting for host…";
      buzzBtn.disabled = true;
    }
  });

  socket.on("game_ended", (data) => {
    const me = (data.leaderboard || []).find((p) => p.id === myPlayerId);
    myResult = me || null;

    endedWinnerText.textContent = data.winner_name
      ? `${data.winner_name} wins!`
      : "Game over — no players to rank.";
    endedDialog.hidden = false;
  });

  socket.on("room_disbanded", (data) => {
    // Inject cumulative data into the modal before showing it
    if (data && data.overall_results && myPlayerId && data.overall_results[myPlayerId]) {
      const o = data.overall_results[myPlayerId];
      
      document.getElementById("overall-games").textContent = o.games_played;
      document.getElementById("overall-won").textContent = o.games_won;
      document.getElementById("overall-score").textContent = fmtScore(o.score);
      document.getElementById("overall-time").textContent = fmtTime(o.time_spoken);
      document.getElementById("overall-correct").textContent = o.correct_jams;
      document.getElementById("overall-wrong").textContent = o.wrong_jams;

      const table = document.getElementById("overall-letters");
      table.innerHTML = "";
      const letters = Object.entries(o.letter_tally || {});
      
      letters.forEach(([letter, count]) => {
        if (count === 0) return;
        const tr = document.createElement("tr");
        const th = document.createElement("th"); th.textContent = letter;
        const td = document.createElement("td"); td.textContent = count;
        tr.appendChild(th); tr.appendChild(td);
        table.appendChild(tr);
      });

      if (o.others_count > 0) {
        const tr = document.createElement("tr");
        const th = document.createElement("th"); th.textContent = "Other";
        const td = document.createElement("td"); td.textContent = o.others_count;
        tr.appendChild(th); tr.appendChild(td);
        table.appendChild(tr);

        if (o.others && o.others.length) {
          const tr2 = document.createElement("tr");
          const td2 = document.createElement("td");
          td2.colSpan = 2;
          td2.style.fontSize = "0.8rem";
          td2.style.color = "var(--color-text-muted)";
          td2.textContent = o.others.join(", ");
          tr2.appendChild(td2);
          table.appendChild(tr2);
        }
      }

      if (table.rows.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 2;
        td.style.color = "var(--color-text-muted)";
        td.textContent = "No mistakes recorded.";
        tr.appendChild(td);
        table.appendChild(tr);
      }
    }
    disbandedDialog.hidden = false;
  });

  socket.on("action_error", (data) => {
    if (!viewGame.hidden) {
      gameStatusLine.textContent = "⚠ " + data.message;
    } else {
      window.alert(data.message);
    }
  });
})();
