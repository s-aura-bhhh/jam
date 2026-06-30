(() => {
  const socket = io();

  let myId = null;
  let roomCode = null;
  let myRes = null;
  const snd = new Audio("/static/buzz.mp3");

  // dom hooks
  const vJoin = document.getElementById("view-join");
  const vWait = document.getElementById("view-waiting");
  const vGame = document.getElementById("view-game");
  const vRes = document.getElementById("view-results");
  const joinForm = document.getElementById("join-form");
  const joinRoomCode = document.getElementById("join-room-code");
  const joinName = document.getElementById("join-name");
  const joinErr = document.getElementById("join-error");
  const waitCode = document.getElementById("waiting-room-code");
  const waitPlayers = document.getElementById("waiting-player-list");
  const gameNum = document.getElementById("game-number-display");
  const gameTimer = document.getElementById("game-timer");
  const banner = document.getElementById("speaker-banner");
  const buzzBtn = document.getElementById("buzz-btn");
  const gameStatus = document.getElementById("game-status-line");
  const gamePlayers = document.getElementById("game-player-list");
  const resScore = document.getElementById("result-score");
  const resTime = document.getElementById("result-time");
  const resCorrect = document.getElementById("result-correct");
  const resWrong = document.getElementById("result-wrong");
  const resLetters = document.getElementById("result-letters");
  const endedDlg = document.getElementById("ended-dialog");
  const endedTxt = document.getElementById("ended-winner-text");
  const endedClose = document.getElementById("ended-close-btn");
  const disbandDlg = document.getElementById("disbanded-dialog");
  const buzzSound = new Audio('/static/sounds/buzz.mp3');

  // utils
  const show = v => [vJoin, vWait, vGame, vRes].forEach(el => el.hidden = el !== v);
  const toTime = n => Number(n).toFixed(2);
  const toScore = n => Number(n).toFixed(2);

  const syncPlayers = (el, list) => {
    el.innerHTML = "";
    list.forEach(p => {
      const li = document.createElement("li");
      if (p.is_speaker) li.classList.add("is-speaker");
      if (p.id === myId) li.classList.add("is-me");

      const nameWrap = document.createElement("span");
      nameWrap.className = "player-name";
      nameWrap.textContent = p.name;

      if (p.is_speaker) {
        const tag = document.createElement("span");
        tag.className = "speaker-tag";
        tag.textContent = "Speaking";
        nameWrap.append(tag);
      }
      
      if (p.id === myId) {
        const tag = document.createElement("span");
        tag.className = "me-tag";
        tag.textContent = "You";
        nameWrap.append(tag);
      }

      const scoreWrap = document.createElement("span");
      scoreWrap.className = "player-score";
      scoreWrap.textContent = toScore(p.score);

      li.append(nameWrap, scoreWrap);
      el.append(li);
    });
  };

  const getMsg = st => {
    if (st.status === "awaiting_decision") return "Buzz received - waiting for host...";
    if (st.status === "awaiting_letter") return "Correct jam! Host selecting mistake...";
    if (st.status === "paused") return "Round paused.";
    if (st.status === "ended") return "Game over!";
    return "";
  };

  const syncBuzzBtn = st => {
    const isSpk = st.speaker_id === myId;
    buzzBtn.disabled = st.status !== "running" || isSpk;
    buzzBtn.textContent = isSpk ? "YOU'RE SPEAKING" : "BUZZ";
  };

  const syncBanner = st => {
    if (!st.speaker_id) {
      banner.textContent = "";
      return;
    }
    const spk = st.players.find(p => p.id === st.speaker_id);
    if (spk) {
      banner.textContent = spk.id === myId ? " You are speaking" : `${spk.name} is speaking`;
    }
  };

  const fillMistakes = (table, data) => {
    table.innerHTML = "";
    let empty = true;
    
    Object.entries(data.letter_tally || {}).forEach(([ltr, cnt]) => {
      if (!cnt) return;
      empty = false;
      const tr = document.createElement("tr");
      const th = document.createElement("th"); th.textContent = ltr;
      const td = document.createElement("td"); td.textContent = cnt;
      tr.append(th, td);
      table.append(tr);
    });

    if (data.others_count > 0) {
      empty = false;
      const tr = document.createElement("tr");
      const th = document.createElement("th"); th.textContent = "Other";
      const td = document.createElement("td"); td.textContent = data.others_count;
      tr.append(th, td);
      table.append(tr);

      if (data.others?.length) {
        const tr2 = document.createElement("tr");
        const td2 = document.createElement("td");
        td2.colSpan = 2;
        td2.style.fontSize = "0.8rem";
        td2.style.color = "var(--gray)";
        td2.textContent = data.others.join(", ");
        tr2.append(td2);
        table.append(tr2);
      }
    }

    if (empty) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 2;
      td.style.color = "var(--gray)";
      td.textContent = "No mistakes recorded.";
      tr.append(td);
      table.append(tr);
    }
  };

  const renderRes = d => {
    resScore.textContent = toScore(d.score);
    resTime.textContent = toTime(d.time_spoken);
    resCorrect.textContent = d.correct_jams;
    resWrong.textContent = d.wrong_jams;
    fillMistakes(resLetters, d);
  };

  // dom events
  joinForm.onsubmit = e => {
    e.preventDefault();
    joinErr.hidden = true;
    const code = joinRoomCode.value.trim();
    const name = joinName.value.trim();
    if (code && name) socket.emit("player_join", { room_code: code, name });
  };

  buzzBtn.onclick = () => socket.emit("buzz");

  endedClose.onclick = () => {
    endedDlg.hidden = true;
    if (myRes) {
      renderRes(myRes);
      show(vRes);
    }
  };

  // socket events
  socket.on("join_success", d => {
    myId = d.player_id;
    roomCode = d.room_code;
    waitCode.textContent = d.room_code;
    show(vWait);
  });

  socket.on("join_error", d => {
    joinErr.textContent = d.message;
    joinErr.hidden = false;
  });

  socket.on("state_update", st => {
    if (st.status === "lobby") {
      waitCode.textContent = st.room_code;
      syncPlayers(waitPlayers, st.players);
      show(vWait);
      return;
    }

    if (!(st.status === "ended" && !vRes.hidden)) show(vGame);
    
    gameNum.textContent = "Game " + st.game_number;
    gameTimer.textContent = toTime(st.remaining);
    gameStatus.textContent = getMsg(st);
    
    syncBanner(st);
    syncBuzzBtn(st);
    syncPlayers(gamePlayers, st.players);
  });

  socket.on("timer_update", d => {
    gameTimer.textContent = toTime(d.remaining);
    if (d.players) syncPlayers(gamePlayers, d.players);
  });

  socket.on("buzzed", d => {
    buzzSound.currentTime = 0;
    buzzSound.play().catch(() => {}); 

    if (d.player_id === myId) {
      gameStatus.textContent = "Buzz received! Waiting for host...";
      buzzBtn.disabled = true;
    }
  });

  socket.on("game_ended", d => {
    myRes = (d.leaderboard || []).find(p => p.id === myId) || null;
    endedTxt.textContent = d.winner_name ? `${d.winner_name} wins!` : "Game over - no players.";
    endedDlg.hidden = false;
  });

  socket.on("room_disbanded", d => {
    if (d?.overall_results && myId && d.overall_results[myId]) {
      const o = d.overall_results[myId];
      document.getElementById("overall-games").textContent = o.games_played;
      document.getElementById("overall-won").textContent = o.games_won;
      document.getElementById("overall-score").textContent = toScore(o.score);
      document.getElementById("overall-time").textContent = toTime(o.time_spoken);
      document.getElementById("overall-correct").textContent = o.correct_jams;
      document.getElementById("overall-wrong").textContent = o.wrong_jams;
      fillMistakes(document.getElementById("overall-letters"), o);
    }
    disbandDlg.hidden = false;
  });

  socket.on("action_error", d => {
    if (!vGame.hidden) {
      gameStatus.textContent = "⚠ " + d.message;
    } else {
      alert(d.message);
    }
  });
})();
