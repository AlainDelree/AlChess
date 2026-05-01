// ── Constantes ────────────────────────────────────────────────────────────

const BASE = "/static/pieces/";
const PIECES = {
  'K': `<img src="${BASE}wK.svg">`,
  'Q': `<img src="${BASE}wQ.svg">`,
  'R': `<img src="${BASE}wR.svg">`,
  'B': `<img src="${BASE}wB.svg">`,
  'N': `<img src="${BASE}wN.svg">`,
  'P': `<img src="${BASE}wP.svg">`,
  'k': `<img src="${BASE}bK.svg">`,
  'q': `<img src="${BASE}bQ.svg">`,
  'r': `<img src="${BASE}bR.svg">`,
  'b': `<img src="${BASE}bB.svg">`,
  'n': `<img src="${BASE}bN.svg">`,
  'p': `<img src="${BASE}bP.svg">`,
};

// ── État global ────────────────────────────────────────────────────────────

let currentFen       = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR";
let lastMove         = null;
let lastMoveColor    = "white";
let bestMove         = null;
let countdownTimer   = null;
let _histMoves       = [];
let _pendingMove     = null;
let currentPlayerColor = "white";
let _selectedColor   = "white";
let _boardOk         = false;

// ── Échiquier principal ────────────────────────────────────────────────────

function buildBoard() {
  const board = document.getElementById("board");
  board.innerHTML = "";

  const rankCoord = document.getElementById("coord-rank");
  rankCoord.innerHTML = "";
  for (let r = 7; r >= 0; r--) {
    const s = document.createElement("span");
    s.textContent = r + 1;
    rankCoord.appendChild(s);
  }
  const fileCoord = document.getElementById("coord-file");
  fileCoord.innerHTML = "";
  "abcdefgh".split("").forEach(f => {
    const s = document.createElement("span");
    s.textContent = f;
    fileCoord.appendChild(s);
  });

  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const sq = document.createElement("div");
      const isLight = (rank + file) % 2 === 1;
      sq.className = `square ${isLight ? 'light' : 'dark'}`;
      sq.id = `sq-${file}-${rank}`;
      board.appendChild(sq);
    }
  }
}

function fenToBoard(fen) {
  const rows = fen.split("/");
  const grid = {};
  for (let rank = 7; rank >= 0; rank--) {
    let file = 0;
    const row = rows[7 - rank];
    for (const ch of row) {
      if (ch >= '1' && ch <= '8') {
        file += parseInt(ch);
      } else {
        grid[`${file}-${rank}`] = ch;
        file++;
      }
    }
  }
  return grid;
}

function lancerAnalyse() {
  const btn = document.getElementById("btn-analyser");
  if (!btn || !btn._movesUci) return;
  btn.textContent = "⏳ Analyse en cours...";
  btn.disabled = true;
  socket.emit("analyser_pgn", { moves: btn._movesUci, niveau: 20 });
}

function renderBoard(fen, from, to, bestFrom, bestTo, feedbackSq, feedbackClass) {
  updateMaterial(fen);
  const grid = fenToBoard(fen);
  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const id = `${file}-${rank}`;
      const sq = document.getElementById(`sq-${id}`);
      if (!sq) continue;
      const piece = grid[id];
      sq.innerHTML = piece ? (PIECES[piece] || piece) : "";
      const isLight = (rank + file) % 2 === 1;
      sq.className = `square ${isLight ? 'light' : 'dark'}`;
      if (from     && id === from)     sq.classList.add("last-move-from");
      if (to       && id === to)       sq.classList.add("last-move-to");
      if (bestFrom && id === bestFrom) sq.classList.add("highlight-best-from");
      if (bestTo   && id === bestTo)   sq.classList.add("highlight-best-to");
      if (feedbackSq && id === feedbackSq && feedbackClass)
        sq.classList.add(`feedback-${feedbackClass}`);
    }
  }
}

function uciToCoords(uci) {
  if (!uci || uci.length < 4) return [null, null];
  const files = "abcdefgh";
  const fromFile = files.indexOf(uci[0]);
  const fromRank = parseInt(uci[1]) - 1;
  const toFile   = files.indexOf(uci[2]);
  const toRank   = parseInt(uci[3]) - 1;
  return [`${fromFile}-${fromRank}`, `${toFile}-${toRank}`];
}

// ── Échiquier review ──────────────────────────────────────────────────────


function buildBoardReview() {
  const board = document.getElementById("board");
  if (!board) return;
  board.innerHTML = "";
  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const sq = document.createElement("div");
      const isLight = (rank + file) % 2 === 1;
      sq.className = `square ${isLight ? 'light' : 'dark'}`;
      sq.id = `sq-${file}-${rank}`;
      board.appendChild(sq);
    }
  }
}

// ── Contrôle Elo ──────────────────────────────────────────────────────────

const ELO_LABELS = [
  [1320, "Débutant"],
  [1400, "Débutant confirmé"],
  [1500, "Joueur confirmé"],
  [1600, "Intermédiaire"],
  [1700, "Intermédiaire+"],
  [1800, "Avancé"],
  [1900, "Avancé+"],
  [2000, "Expert"],
  [2200, "Maître"],
  [2400, "Grand Maître"],
  [3190, "Niveau max"],
];

function eloLabel(elo) {
  let label = ELO_LABELS[0][1];
  for (const [seuil, lbl] of ELO_LABELS) {
    if (elo >= seuil) label = lbl;
  }
  return label;
}

function adjustElo(delta) {
  const input = document.getElementById("cfg-elo");
  let val = parseInt(input.value) + delta;
  val = Math.max(1320, Math.min(3190, val));
  input.value = val;
  _updateEloLabel(val);
}

function clampElo() {
  const input = document.getElementById("cfg-elo");
  let val = parseInt(input.value);
  if (isNaN(val)) return;
  val = Math.max(1320, Math.min(3190, val));
  _updateEloLabel(val);
}

function _updateEloLabel(elo) {
  const el = document.getElementById("cfg-elo-label");
  if (el) el.textContent = `~${elo} Elo — ${eloLabel(elo)}`;
  const analyseLbl = document.getElementById("cfg-analyse-label");
  const analyseChk = document.getElementById("cfg-analyse");
  if (analyseLbl && analyseChk) {
    analyseLbl.textContent = analyseChk.checked ? "Activée" : "Désactivée";
  }
}

function selectColor(color) {
  _selectedColor = color;
  document.getElementById("cfg-white").classList.toggle("selected",  color === "white");
  document.getElementById("cfg-black").classList.toggle("selected",  color === "black");
  document.getElementById("cfg-random").classList.toggle("selected", color === "random");
}

let _selectedEngine = "stockfish";

function selectEngine(engine) {
  _selectedEngine = engine;
  document.getElementById("cfg-engine-stockfish").classList.toggle("selected", engine === "stockfish");
  document.getElementById("cfg-engine-maia").classList.toggle("selected",      engine === "maia");
  document.getElementById("cfg-engine-rodent").classList.toggle("selected",    engine === "rodent");
  document.getElementById("cfg-section-stockfish").style.display = engine === "stockfish" ? "" : "none";
  document.getElementById("cfg-section-maia").style.display      = engine === "maia"      ? "" : "none";
  document.getElementById("cfg-section-rodent").style.display    = engine === "rodent"    ? "" : "none";
}

const _rodentLabels = [
  [800,  "800 Elo — Grand débutant"],
  [1000, "1000 Elo — Débutant"],
  [1200, "1200 Elo — Débutant+"],
  [1400, "1400 Elo — Intermédiaire bas"],
  [1600, "1600 Elo — Intermédiaire"],
  [1800, "1800 Elo — Avancé"],
  [2000, "2000 Elo — Expert"],
  [2200, "2200 Elo — Maître"],
  [2400, "2400 Elo — Maître international"],
  [2800, "2800 Elo — Elite"],
];

function _updateRodentLabel(val) {
  const el = document.getElementById("cfg-rodent-elo-label");
  if (!el) return;
  let label = val + " Elo";
  for (const [threshold, text] of _rodentLabels) {
    if (val <= threshold) { label = text; break; }
  }
  el.textContent = label;
}

function adjustRodentElo(delta) {
  const input = document.getElementById("cfg-rodent-elo");
  let val = parseInt(input.value) + delta;
  val = Math.max(800, Math.min(2800, val));
  input.value = val;
  _updateRodentLabel(val);
}

function clampRodentElo() {
  const input = document.getElementById("cfg-rodent-elo");
  let val = parseInt(input.value) || 800;
  val = Math.max(800, Math.min(2800, val));
  input.value = val;
  _updateRodentLabel(val);
}

function startGame() {
  const player    = document.getElementById("cfg-player").value.trim() || "Anonyme";
  const elo       = parseInt(document.getElementById("cfg-elo").value) || 1500;
  const pause     = document.getElementById("cfg-pause").value;
  const analyse   = document.getElementById("cfg-analyse")?.checked !== false;
  const bip       = document.getElementById("cfg-bip")?.checked === true;
  const maiaElo   = parseInt(document.getElementById("cfg-maia-elo")?.value) || 1500;
  const rodentElo    = parseInt(document.getElementById("cfg-rodent-elo")?.value) || 800;
  const rodentSimple = document.getElementById("cfg-rodent-simple")?.checked === true;
  sendAction({
    type: "start",
    player,
    color: _selectedColor,
    level: 5,
    elo,
    pause,
    analyse_active: analyse,
    bip_active: bip,
    engine_type: _selectedEngine,
    maia_elo: maiaElo,
    rodent_elo: rodentElo,
    rodent_simple: rodentSimple,
  });
}

// ── Barre WDL ─────────────────────────────────────────────────────────────

function updateWdlBar(wdl) {
  const container = document.getElementById("wdl-bar-container");
  if (!container) return;
  if (!wdl) { container.style.display = "none"; return; }
  container.style.display = "block";
  document.getElementById("wdl-win").style.width  = wdl.win  + "%";
  document.getElementById("wdl-draw").style.width = wdl.draw + "%";
  document.getElementById("wdl-loss").style.width = wdl.loss + "%";
  document.getElementById("wdl-win-pct").textContent  = wdl.win  > 5 ? wdl.win  + "%" : "";
  document.getElementById("wdl-draw-pct").textContent = wdl.draw > 5 ? wdl.draw + "%" : "";
  document.getElementById("wdl-loss-pct").textContent = wdl.loss > 5 ? wdl.loss + "%" : "";
}

// ── SocketIO ──────────────────────────────────────────────────────────────

const socket = io();

socket.on("board_error", (data) => {
  const sub = document.querySelector(".menu-subtitle");
  if (sub) { sub.textContent = "⚠ Échiquier non détecté — vérifiez l'USB et allumez le plateau puis redémarrez le jeu"; sub.style.color = "#e94560"; }
  const btn = document.getElementById("btn-reconnect");
  if (btn) { btn.textContent = "⟳ Reconnecter l'échiquier"; btn.disabled = false; btn.style.opacity = "1"; btn.style.cursor = "pointer"; btn.style.background = "#e94560"; btn.style.color = "white"; }
});

socket.on("board_ok", () => {
  _boardOk = true;
  const sub = document.querySelector(".menu-subtitle");
  if (sub) { sub.textContent = "Échiquier connecté — choisissez un mode"; sub.style.color = ""; }
  document.querySelectorAll(".menu-btn[data-needs-board]")
    .forEach(btn => { btn.disabled = false; });
  const btn = document.getElementById("btn-reconnect");
  if (btn) { btn.textContent = "✓ Échiquier connecté"; btn.disabled = true; btn.style.opacity = "0.5"; btn.style.cursor = "default"; btn.style.background = ""; }
});

socket.on("connect", () => {
  document.getElementById("status-dot").classList.add("connected");
  document.getElementById("status-text").textContent = "Connecté";
});

socket.on("disconnect", () => {
  document.getElementById("status-dot").classList.remove("connected");
  document.getElementById("status-text").textContent = "Déconnecté";
});

socket.on("status", (data) => {
  document.getElementById("status-text").textContent = data.message;
});

socket.on("app_state", (data) => {
  // Si game_over avec skip=true (back_menu), on ignore complètement
  if (data.state === "game_over" && data.skip) return;
  document.getElementById("screen-menu").style.display          = data.state === "menu"          ? "flex" : "none";
  document.getElementById("screen-config").style.display        = data.state === "config"        ? "flex" : "none";
  document.getElementById("screen-config-humain").style.display = data.state === "config_humain" ? "flex" : "none";
  document.getElementById("screen-connecting").style.display = data.state === "connecting" ? "flex" : "none";
  document.getElementById("screen-pos-init").style.display = data.state === "position_initiale" ? "flex" : "none";
  if (data.state === "position_initiale" && data.fen) {
    renderBoardPosInit(data.fen);
  }
  const isGame = data.state === "playing" || (data.state === "game_over" && !data.skip) || data.state === "paused";
  document.getElementById("screen-game").style.display = isGame ? "grid" : "none";
  document.getElementById("panel-playing").style.display  = data.state === "playing"                    ? "flex" : "none";
  document.getElementById("panel-gameover").style.display = (data.state === "game_over" && !data.skip) ? "flex" : "none";
  document.getElementById("panel-pause").style.display    = data.state === "paused"                     ? "flex" : "none";
  if (data.state === "config" && data.last_player) {
    document.getElementById("cfg-player").value = data.last_player;
  }

  if (data.state === "game_over" && !data.skip) {
    // Restaurer le fond par défaut — l'écran d'analyse est neutre
    document.body.setAttribute("style", "background: #1a1a2e !important;");
    if (data.title) document.getElementById("gameover-title").textContent = data.title;
    // data.result peut contenir un score ("0-1", "1-0", "1/2-1/2") ou un message texte
    const isScore = data.result && /^(1-0|0-1|1\/2-1\/2|\*)$/.test(data.result.trim());
    document.getElementById("gameover-result").textContent = isScore ? data.result : "";
    document.getElementById("rv-game-info").textContent    = isScore ? "" : (data.result || "");
    // Mettre à jour _gameSource si présent dans le payload
    if (data.source) _gameSource = data.source;
    // Toujours utiliser l'historique du serveur — source de vérité absolue
    if (data.history_fen && data.history_fen.length > 0) {
      reviewFens = data.history_fen;
    }
    if (data.history_moves && data.history_moves.length > 0)
      reviewMoves = data.history_moves;
    reviewIdx = Math.max(0, reviewFens.length - 1);
    // Détecter si déjà analysé
    _isAnalysed = reviewMoves.some(m => m.qualite && m.qualite !== "bon");
    _renderHistory();
    if (reviewFens.length > 0) { _setNavControls(true); renderReview(); }
    const cardNavSave = document.getElementById("card-nav-save");
    if (cardNavSave) cardNavSave.style.display = "";
    _updateActionButtons();
  }
  if (data.state === "menu") {
    _gameSource = "externe";
    _viderAnalyse();
    // Restaurer la couleur de fond par défaut
    document.body.setAttribute("style", "background: #1a1a2e !important;");
    // Réactiver les boutons si l'échiquier était déjà connecté
    if (_boardOk) {
      document.querySelectorAll(".menu-btn[data-needs-board]")
        .forEach(btn => { btn.disabled = false; });
    }
    // Filet de sécurité : si les boutons sont encore grisés après 1.5s
    // transformer le bouton reconnect en bouton de secours
    setTimeout(() => {
      const needsBoard = document.querySelectorAll(".menu-btn[data-needs-board]");
      const stillBlocked = Array.from(needsBoard).some(b => b.disabled);
      const btn = document.getElementById("btn-reconnect");
      if (stillBlocked && _boardOk && btn) {
        btn.textContent = "⟳ Débloquer les boutons";
        btn.disabled = false;
        btn.style.opacity = "1";
        btn.style.cursor = "pointer";
        btn.style.background = "#e94560";
        btn.style.color = "white";
      }
    }, 1500);
  }
});

socket.on("undo_move", (data) => {
  // Juste mettre à jour la position courante — reviewFens sera reconstruit au game_over
  currentFen = data.fen || currentFen;
  lastMove   = null;
  renderBoard(currentFen, null, null, null, null, null, null);
  hideFeedback();
});

socket.on("move", (data) => {
  currentFen    = data.fen;
  lastMove      = data.uci;
  lastMoveColor = data.color;
  bestMove      = null;
  reviewFens.push(data.fen);
  // En HH pas d'analyse → qualite reste null (pas de symbole)
  reviewMoves.push({ san: data.san, color: data.color, qualite: data.qualite || null, uci: data.uci });
  reviewIdx = reviewFens.length - 1;
  _renderHistory();
  // _pendingMove : pour attendre la qualité du coup humain
  if (data.color === currentPlayerColor) {
    _pendingMove = { san: data.san, color: data.color, qualite: null };
  } else {
    _pendingMove = null;
  }

  const [from, to] = uciToCoords(data.uci);
  renderBoard(currentFen, from, to, null, null, null, null);
  hideFeedback();
  stopCountdown();

  // Mettre à jour la barre WDL si présente (coup moteur)
  if (data.wdl) updateWdlBar(data.wdl);

  const turnInfo = document.getElementById("turn-info");
  turnInfo.textContent = `${data.player} (${data.color === 'white' ? 'Blancs' : 'Noirs'}) a joué ${data.san}`;
  turnInfo.className = data.color;
});

socket.on("turn", (data) => {
  const btnAbandon = document.querySelector(".btn-warning");
  if (btnAbandon) {
    btnAbandon.disabled    = !data.is_human;
    btnAbandon.style.opacity = data.is_human ? "1" : "0.4";
  }
  const btnPause = document.getElementById("btn-pause");
  if (btnPause) {
    btnPause.disabled = !data.is_human;
    btnPause.style.opacity = data.is_human ? "1" : "0.4";
  }
  const btnNulle = document.getElementById("btn-nulle");
  if (btnNulle) {
    btnNulle.disabled = !data.is_human;
    btnNulle.style.opacity = data.is_human ? "1" : "0.4";
  }
  // btn-reprendre géré par showFeedback/hideFeedback uniquement
  if (!data.player || !data.color) return;
  const turnInfo = document.getElementById("turn-info");
  if (data.in_check) {
    turnInfo.textContent = `⚠ Échec ! Au tour de ${data.player} (${data.color === 'white' ? 'Blancs' : 'Noirs'})`;
    turnInfo.className = "warning";
  } else {
    turnInfo.textContent = `Au tour de ${data.player} (${data.color === 'white' ? 'Blancs' : 'Noirs'})`;
    turnInfo.className = data.color;
  }

});

socket.on("feedback", (data) => { showFeedback(data); });

socket.on("swap_color", (data) => {
  const isWhite  = data.color === "white";
  const opponent = data.opponent || `Stockfish ~${data.level * 100}elo`;
  const topName  = document.getElementById("player-top-name");
  const botName  = document.getElementById("player-bottom-name");
  topName.textContent = isWhite ? opponent : data.player;
  botName.textContent = isWhite ? data.player : opponent;
  topName.style.color = isWhite ? "#555" : "#ddd";
  botName.style.color = isWhite ? "#ddd" : "#555";
});

socket.on("best_move", (data) => {
  bestMove = data.uci;
  const [bFrom, bTo] = uciToCoords(data.uci);
  const [lFrom, lTo] = uciToCoords(lastMove);
  renderBoard(currentFen, lFrom, lTo, bFrom, bTo, null, null);
});

socket.on("qualite", (data) => {
  if (_pendingMove && _pendingMove.san === data.san) {
    _pendingMove.qualite = data.qualite;
    _pendingMove = null;
  }
  // Mettre à jour la qualité dans reviewMoves si le san correspond
  const idx = reviewMoves.findIndex(m => m.san === data.san && (m.qualite === null || m.qualite === "bon"));
  if (idx !== -1) {
    reviewMoves[idx].qualite = data.qualite;
    _renderHistory();
    if (data.qualite && data.qualite !== "bon") {
      _isAnalysed = true;
      _updateActionButtons();
      _updateReviewBestMoveBtn();
    }
  }
  // Mettre à jour la barre WDL après coup humain
  if (data.wdl) updateWdlBar(data.wdl);
});

socket.on("popup", (data) => {
  // Popup simple avec bouton OK — utilisé pour échec et mat, pat, etc.
  document.getElementById("modal-title").textContent = data.message || "Fin de partie";
  const std  = document.getElementById("modal-btns-standard");
  const coul = document.getElementById("modal-btns-couleur");
  if (std)  std.style.display  = "flex";
  if (coul) coul.style.display = "none";
  const btn = document.getElementById("modal-confirm");
  btn.textContent = "OK";
  btn.className   = "btn btn-reprendre";
  btn.onclick = () => { fermerModal(); };
  // Cacher le bouton Annuler
  const cancelBtn = std?.querySelector(".btn-continuer");
  if (cancelBtn) cancelBtn.style.display = "none";
  document.getElementById("modal-overlay").classList.add("open");
  // Remettre Annuler visible quand on ferme
  btn.onclick = () => {
    fermerModal();
    if (cancelBtn) cancelBtn.style.display = "";
  };
});

socket.on("game_over", (data) => {
  if (data.skip) return;  // back_menu — on ignore
  hideFeedback();
  stopCountdown();
  _gameSource = data.source || "externe";
  if (data.title)  document.getElementById("gameover-title").textContent  = data.title;
  if (data.result) document.getElementById("gameover-result").textContent = data.result;
  document.getElementById("rv-game-info").textContent = "";
  const fenToRender = reviewFens[reviewIdx] || currentFen || "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR";
  renderBoard(fenToRender, null, null, null, null, null, null);
});

socket.on("init", (data) => {
  _gameMode = "pedagogique";
  currentPlayerColor = data.color || "white";
  _pendingMove = null;
  _histMoves   = [];
  reviewFens  = [data.fen || currentFen];
  reviewMoves = [];
  reviewIdx   = 0;
  currentFen   = data.fen || currentFen;
  const isWhite   = data.color === "white";
  const opponent  = data.opponent || `Stockfish ~${data.elo || data.level * 100}elo`;
  const topName = document.getElementById("player-top-name");
  const botName = document.getElementById("player-bottom-name");
  topName.textContent = isWhite ? opponent : data.player;
  botName.textContent = isWhite ? data.player : opponent;
  // Couleur du nom selon les pièces jouées : noir=gris, blanc=clair
  topName.style.color = isWhite ? "#555" : "#ddd";
  botName.style.color = isWhite ? "#ddd" : "#555";

  // Couleur de fond selon le moteur
  if (data.engine_type === "maia") {
    document.body.setAttribute("style", "background: #2e1a1e !important;");
  } else if (data.engine_type === "rodent") {
    document.body.setAttribute("style", "background: #1a2e1a !important;");
  } else {
    document.body.setAttribute("style", "background: #1a1a2e !important;");
  }

  renderBoard(currentFen, null, null, null, null, null, null);
  document.getElementById("game-subtitle").textContent = isWhite
    ? `${data.player} contre ${opponent}`
    : `${opponent} contre ${data.player}`;
  // Cacher la barre WDL au départ
  updateWdlBar(null);
  // Cacher barre si analyse désactivée
  if (!data.analyse) {
    const wdlBar = document.getElementById("wdl-bar-container");
    if (wdlBar) wdlBar.style.display = "none";
  }
  const titleEl = document.getElementById("panel-playing-title");
  if (titleEl) titleEl.textContent = data.analyse === false ? "Partie libre" : "Partie Pédagogique";
  const pauseRow = document.getElementById("pause-select-row");
  if (pauseRow) pauseRow.style.display = data.analyse === false ? "none" : "flex";
  const btnPause = document.getElementById("btn-pause");
  if (btnPause) { btnPause.style.display = ""; }
  const btnNulle = document.getElementById("btn-nulle");
  if (btnNulle) btnNulle.textContent = "🤝 Partie Nulle";
  document.getElementById("turn-info").textContent = "En attente...";
  const pauseSel = document.getElementById("pause-select");
  if (pauseSel && data.pause) {
    pauseSel.value = data.pause;
  }
  document.getElementById("historique").innerHTML = "";
  hideFeedback();
});

socket.on("init_hh", (data) => {
  _gameMode = "humain";
  currentPlayerColor = "white";
  _pendingMove = null;
  reviewFens  = [data.fen || currentFen];
  reviewMoves = [];
  reviewIdx   = 0;
  currentFen  = data.fen || currentFen;
  const topName = document.getElementById("player-top-name");
  const botName = document.getElementById("player-bottom-name");
  topName.textContent  = data.black || "Noirs";
  botName.textContent  = data.white || "Blancs";
  topName.style.color  = "#777";
  botName.style.color  = "#ddd";
  document.getElementById("game-subtitle").innerHTML =
    `<span style="color:#f0f0f0;">♔ ${data.white}</span>`+
    `<span style="color:#666; margin:0 8px;">vs</span>`+
    `<span style="color:#888;">♚ ${data.black}</span>`;
  const titleElHH = document.getElementById("panel-playing-title");
  if (titleElHH) titleElHH.textContent = "Humain vs Humain";
  const pauseRowHH = document.getElementById("pause-select-row");
  if (pauseRowHH) pauseRowHH.style.display = "none";
  const btnPauseHH = document.getElementById("btn-pause");
  if (btnPauseHH) { btnPauseHH.style.display = ""; }
  const btnNulleHH = document.getElementById("btn-nulle");
  if (btnNulleHH) btnNulleHH.textContent = "🤝 Proposer Nulle";
  document.getElementById("turn-info").textContent = "En attente...";
  renderBoard(currentFen, null, null, null, null, null, null);
  hideFeedback();
  document.getElementById("historique").innerHTML = "";
});

socket.on("swap_color_hh", (data) => {
  const topName = document.getElementById("player-top-name");
  const botName = document.getElementById("player-bottom-name");
  topName.textContent = data.black || "Noirs";
  botName.textContent = data.white || "Blancs";
});

socket.on("history", (data) => {
  _pendingMove = null;
});
socket.on("nulle_refusee", (data) => {
  afficherToast("🤝 Nulle refusée — " + (data.reason || "Stockfish estime avoir l'avantage."), "warning");
});

socket.on("pgn_sauvegarde", (data) => {
  const nom = data.path ? data.path.split("/").pop() : "fichier";
  afficherToast("💾 Sauvegardé : " + nom, "success");
});

socket.on("position_initiale", (data) => {
  document.getElementById("screen-menu").style.display          = "none";
  document.getElementById("screen-config").style.display        = "none";
  document.getElementById("screen-config-humain").style.display = "none";
  document.getElementById("screen-connecting").style.display = "none";
  document.getElementById("screen-game").style.display       = "none";
  document.getElementById("screen-pos-init").style.display   = "flex";
  if (data.fen) renderBoardPosInit(data.fen);
});

function afficherToast(message, type) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.className = "toast toast-" + (type || "info") + " show";
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.classList.remove("show"); }, 4000);
}

function _updateActionButtons() {
  const btnA     = document.getElementById("btn-analyser");
  const btnD     = document.getElementById("btn-telecharger");
  const btnV     = document.getElementById("btn-vider-analyse");
  const saveBlock = document.getElementById("card-save-block");
  const hasGame  = reviewFens.length > 1;
  if (btnA) btnA.style.display = (hasGame && !_isAnalysed) ? "inline-block" : "none";
  if (btnD) btnD.style.display = _isAnalysed ? "inline-block" : "none";
  if (btnV) btnV.style.display = hasGame ? "inline-block" : "none";
  // card-save-block : visible si partie NicLink OU si partie analysée
  if (saveBlock) saveBlock.style.display = (_gameSource === "niclink" || _isAnalysed) ? "" : "none";
}

function _viderAnalyse() {
  reviewFens = []; reviewMoves = []; reviewIdx = 0;
  _isAnalysed = false;
  _stopAutoPlay();
  _setNavControls(false);
  const top = document.getElementById("player-top-name");
  const bot = document.getElementById("player-bottom-name");
  if (top) top.textContent = "";
  if (bot) bot.textContent = "";
  const titre  = document.getElementById("gameover-title");
  const result = document.getElementById("gameover-result");
  const info   = document.getElementById("rv-game-info");
  if (titre)  titre.textContent  = "Analyse de partie";
  if (result) result.textContent = "";
  if (info)   info.textContent   = "Importez un fichier PGN";
  const btnA      = document.getElementById("btn-analyser");
  const btnD      = document.getElementById("btn-telecharger");
  const btnV      = document.getElementById("btn-vider-analyse");
  const saveBlock = document.getElementById("card-save-block");
  if (btnA) { btnA.style.display = "none"; btnA.textContent = "🔍 Analyser la partie"; btnA.disabled = false; delete btnA._movesUci; }
  if (btnD) btnD.style.display = "none";
  if (btnV) btnV.style.display = "none";
  if (saveBlock) saveBlock.style.display = "none";
  renderBoard("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR", null, null, null, null, null, null);
  const hist = document.getElementById("historique");
  if (hist) hist.innerHTML = "";
  const mi = document.getElementById("review-move-info");
  if (mi) mi.innerHTML = "";
  const ms = document.getElementById("review-move-san");
  if (ms) ms.textContent = "";
  const fi = document.getElementById("pgn-file-input");
  if (fi) fi.value = "";
}

function _buildBoardPosInit() {
  const board = document.getElementById("board-pos-init");
  if (!board) return;
  board.innerHTML = "";
  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const sq = document.createElement("div");
      sq.className = `square ${(rank + file) % 2 === 1 ? 'light' : 'dark'}`;
      sq.id = `pi-${file}-${rank}`;
      board.appendChild(sq);
    }
  }
}

function renderBoardPosInit(fen) {
  const INITIAL_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR";
  const grid        = fenToBoard(fen);
  const gridInit    = fenToBoard(INITIAL_FEN);
  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const id  = `${file}-${rank}`;
      const sq  = document.getElementById(`pi-${id}`);
      if (!sq) continue;
      const piece = grid[id];
      sq.innerHTML = piece ? (PIECES[piece] || piece) : "";
      const isLight = (rank + file) % 2 === 1;
      // Case incorrecte = pièce actuelle différente de l'initiale
      const correct = (grid[id] || "") === (gridInit[id] || "");
      if (!correct) {
        sq.className = `square ${isLight ? 'light' : 'dark'} pos-init-error`;
      } else {
        sq.className = `square ${isLight ? 'light' : 'dark'}`;
      }
    }
  }
}
// ── Feedback ──────────────────────────────────────────────────────────────

const LABELS = {
  bon:         "✓ Bon coup",
  imprecision: "?! Imprécision",
  erreur:      "? Erreur",
  blunder:     "?? Gaffe",
};

// Séquence punitive stockée lors du feedback
let _punishmentLine = [];
let _fenAvantCoup   = null;

function showFeedback(data) {
  const card   = document.getElementById("feedback-card");
  const box    = document.getElementById("feedback-box");
  const label  = document.getElementById("feedback-label");
  const detail = document.getElementById("feedback-detail");

  if (data.pause_mode === "bloquant") {
    card.style.display = "block";
    box.style.display  = "block";
    box.className      = data.qualite;
    label.textContent  = LABELS[data.qualite] || data.qualite;
    detail.textContent = `${data.san} — ${data.delta_cp}cp de perte`;
    document.getElementById("btn-best").disabled      = !data.best_move_uci;
    document.getElementById("btn-continuer").disabled = false;
    // Bouton séquence — actif si une ligne punitive est disponible
    const btnSeq = document.getElementById("btn-sequence");
    if (btnSeq) {
      _punishmentLine = data.punishment_line || [];
      _fenAvantCoup   = data.fen_avant_coup  || null;
      btnSeq.disabled = _punishmentLine.length === 0;
    }
    // Cacher Actions pendant la pause pédagogique
    const cardActions = document.getElementById("card-actions");
    if (cardActions) cardActions.style.display = "none";
  }

  // btn-reprendre actif uniquement pendant la pause pédagogique
  const btnR = document.getElementById("btn-reprendre");
  btnR.disabled     = false;
  btnR.style.opacity = "1";

  if (data.best_move_uci) {
    bestMove = data.best_move_uci;
    // Activer le bouton meilleur coup dans le panel pause aussi
    const btnPM = document.getElementById("btn-pause-meilleur");
    if (btnPM) { btnPM.disabled = false; btnPM.style.opacity = "1"; }
  }

  if (_pendingMove) {
    _pendingMove.qualite = data.qualite;
    _pendingMove = null;
  }

  if (lastMove && data.pause_mode === "bloquant") {
    const [lFrom, lTo] = uciToCoords(lastMove);
    const [, to]       = uciToCoords(lastMove);
    renderBoard(currentFen, lFrom, lTo, null, null, to, data.qualite);
  }
}

function hideFeedback() {
  document.getElementById("feedback-card").style.display = "none";
  document.getElementById("feedback-box").style.display  = "none";
  document.getElementById("btn-best").disabled      = true;
  document.getElementById("btn-continuer").disabled = true;
  const btnSeq = document.getElementById("btn-sequence");
  if (btnSeq) btnSeq.disabled = true;
  const btnPM = document.getElementById("btn-pause-meilleur");
  if (btnPM) { btnPM.disabled = true; btnPM.style.opacity = "0.4"; }
  const btnReprendre = document.getElementById("btn-reprendre");
  if (btnReprendre) {
    btnReprendre.disabled    = true;
    btnReprendre.style.opacity = "0.4";
  }
  // Remettre card-actions visible
  const cardActions = document.getElementById("card-actions");
  if (cardActions) cardActions.style.display = "flex";
}

// ── Séquence punitive ─────────────────────────────────────────────────────

function jouerSequencePunitive() {
  if (!_punishmentLine || _punishmentLine.length === 0 || !_fenAvantCoup) return;

  const btnSeq = document.getElementById("btn-sequence");
  if (btnSeq) btnSeq.disabled = true;

  const fens = [currentFen];
  try {
    // Partir du FEN avant le coup humain pour avoir le bon contexte (tour, droits de roque, etc.)
    // _fenAvantCoup est le FEN complet Stockfish envoyé par le serveur
    const game = new Chess(_fenAvantCoup);
    // Rejouer d'abord le coup humain (lastMove)
    if (lastMove) {
      game.move({ from: lastMove.slice(0,2), to: lastMove.slice(2,4),
                  promotion: lastMove.length === 5 ? lastMove[4] : undefined });
    }
    // Puis appliquer la séquence punitive
    for (const uci of _punishmentLine) {
      const from = uci.slice(0, 2);
      const to   = uci.slice(2, 4);
      const promo = uci.length === 5 ? uci[4] : undefined;
      const ok = game.move({ from, to, promotion: promo });
      if (!ok) break;
      fens.push(game.fen().split(" ")[0]);
    }
  } catch(e) {
    console.error("jouerSequencePunitive erreur:", e);
    if (btnSeq) btnSeq.disabled = false;
    return;
  }

  // Animer les positions une par une
  let idx = 0;
  function step() {
    if (idx >= fens.length) {
      // Revenir à la position courante après 1.5s
      setTimeout(() => {
        renderBoard(currentFen, null, null, null, null, null, null);
        if (btnSeq) btnSeq.disabled = false;
      }, 1500);
      return;
    }
    const fen = fens[idx];
    const prevFen = idx > 0 ? fens[idx-1] : null;
    // Calculer from/to depuis le coup UCI si possible
    let from = null, to = null;
    if (idx > 0 && idx - 1 < _punishmentLine.length) {
      const uci = _punishmentLine[idx - 1];
      [from, to] = [uci.slice(0, 2), uci.slice(2, 4)];
    }
    renderBoard(fen, from, to, null, null, to, null);
    idx++;
    setTimeout(step, 1000);
  }
  step();
}

// ── Historique ────────────────────────────────────────────────────────────

function addToHistory(san, qualite, color) {
  _histMoves.push({ san, qualite, color: color || "white" });
  _renderHistory();
}

function qualiteColor(qualite) {
  switch(qualite) {
    case "imprecision": return "#f0a500";
    case "erreur":      return "#e05000";
    case "blunder":     return "#9b00e0";
    default:            return "#ccc";
  }
}
function qualiteSymbole(qualite) {
  switch(qualite) {
    case "imprecision": return "?!";
    case "erreur":      return "?";
    case "blunder":     return "??";
    default:            return "";
  }
}
function qualiteAnnotation(qualite, delta_cp) {
  const sym = { "bon": "✓", "imprecision": "?!", "erreur": "?", "blunder": "??" };
  const s = sym[qualite] || "✓";
  const cp = delta_cp !== undefined ? ` ${delta_cp}cp` : "";
  return `{ ${s}${cp} }`;
}

function telechargerPgn() {
  // Reconstruire le PGN avec commentaires
  let pgn = "";
  // Headers
  const white = document.getElementById("player-bottom-name").textContent;
  const black = document.getElementById("player-top-name").textContent;
  const result = document.getElementById("gameover-result").textContent.trim() || "*";
  pgn += `[White "${white}"]\n[Black "${black}"]\n[Result "${result}"]\n\n`;
  // Coups
  for (let i = 0; i < reviewMoves.length; i++) {
    const m = reviewMoves[i];
    if (m.color === "white") pgn += `${Math.floor(i/2)+1}. `;
    pgn += m.san;
    if (m.qualite) pgn += ` ${qualiteAnnotation(m.qualite, m.delta_cp)}`;
    pgn += " ";
  }
  pgn += result;
  // Téléchargement
  const blob = new Blob([pgn], { type: "text/plain" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `${white}_vs_${black}_analyse.pgn`;
  a.click();
  URL.revokeObjectURL(url);
}
function sauvegarderNicLink() {
  const white  = document.getElementById("player-bottom-name").textContent;
  const black  = document.getElementById("player-top-name").textContent;
  const result = document.getElementById("gameover-result").textContent.trim() || "*";
  // Reconstruire le PGN enrichi
  let moves_pgn = "";
  for (let i = 0; i < reviewMoves.length; i++) {
    const m = reviewMoves[i];
    if (m.color === "white") moves_pgn += `${Math.floor(i/2)+1}. `;
    moves_pgn += m.san;
    if (m.qualite) moves_pgn += ` ${qualiteAnnotation(m.qualite, m.delta_cp)}`;
    moves_pgn += " ";
  }
  moves_pgn += result;
  // La valeur du select = "Stockfish-Pedagogique" ou "Humain-Club" etc.
  const saveType = document.getElementById("save-type")?.value || "Stockfish-Pedagogique";
  socket.emit("save_pgn_externe", {
    white, black, result, moves_pgn,
    save_type: saveType,
  });
}
function _renderHistory() {
  const hist = document.getElementById("historique");
  if (!hist) return;
  const sym = { bon: "✓", imprecision: "?!", erreur: "?", blunder: "??" };
  // null = pas d'analyse (HH) → pas de symbole

  // Séparer les coups par couleur (utilise m.color, pas l'index)
  const whites = reviewMoves.filter(m => m.color === "white");
  const blacks = reviewMoves.filter(m => m.color === "black");
  const total  = Math.max(whites.length, blacks.length);

  let html = '<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">';
  html += '<tr><th style="color:#666;width:24px;text-align:right;padding-right:6px"></th>';
  html += '<th style="color:#aaa;text-align:left;padding:2px 4px">Blancs</th>';
  html += '<th style="color:#aaa;text-align:left;padding:2px 4px">Noirs</th></tr>';

  for (let i = 0; i < total; i++) {
    const w = whites[i];
    const b = blacks[i];
    html += `<tr><td style="color:#555;text-align:right;padding-right:6px;font-size:0.75rem">${i+1}.</td>`;
    const wq = w?.qualite || "bon";
    const bq = b?.qualite || "bon";
    const wsym = w?.qualite ? (sym[wq] || "") : "";
    const bsym = b?.qualite ? (sym[bq] || "") : "";
    html += w ? `<td><span class="move-chip ${wq}">${w.san}${wsym}</span></td>` : `<td></td>`;
    html += b ? `<td><span class="move-chip ${bq}">${b.san}${bsym}</span></td>` : `<td></td>`;
    html += `</tr>`;
  }
  html += '</table>';
  hist.innerHTML = html;
  hist.scrollTop = hist.scrollHeight;
}

// ── Countdown ─────────────────────────────────────────────────────────────

function startCountdown(seconds) {
  const el = document.getElementById("countdown");
  el.style.display = "block";
  let remaining = seconds;
  el.textContent = remaining;
  countdownTimer = setInterval(() => {
    remaining--;
    el.textContent = remaining;
    if (remaining <= 0) {
      stopCountdown();
      sendAction({ type: "continuer" });
    }
  }, 1000);
}

function stopCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }
  document.getElementById("countdown").style.display = "none";
}

// ── Modal de confirmation ─────────────────────────────────────────────────

function ouvrirModalAbandonner() {
  const std  = document.getElementById("modal-btns-standard");
  const coul = document.getElementById("modal-btns-couleur");
  if (_gameMode === "humain") {
    document.getElementById("modal-title").textContent = "Qui abandonne la partie ?";
    // Mettre les vrais noms sur les boutons
    const btnBlanc = document.getElementById("modal-btn-blanc");
    const btnNoir  = document.getElementById("modal-btn-noir");
    const nomBlanc = document.getElementById("player-bottom-name")?.textContent || "Blancs";
    const nomNoir  = document.getElementById("player-top-name")?.textContent  || "Noirs";
    if (btnBlanc) { btnBlanc.textContent = `🏳 ${nomBlanc} abandonne`; }
    if (btnNoir)  { btnNoir.textContent  = `🏳 ${nomNoir} abandonne`; }
    if (std)  std.style.display  = "none";
    if (coul) coul.style.display = "flex";
  } else {
    document.getElementById("modal-title").textContent = "Abandonner la partie ?";
    const btn = document.getElementById("modal-confirm");
    btn.textContent = "Confirmer l'abandon";
    btn.className   = "btn btn-warning";
    btn.onclick = () => { fermerModal(); sendAction({ type: "abandonner" }); };
    if (std)  std.style.display  = "flex";
    if (coul) coul.style.display = "none";
  }
  document.getElementById("modal-overlay").classList.add("open");
}

function ouvrirModalNulle() {
  const std  = document.getElementById("modal-btns-standard");
  const coul = document.getElementById("modal-btns-couleur");
  if (std)  std.style.display  = "flex";
  if (coul) coul.style.display = "none";
  const btn = document.getElementById("modal-confirm");
  if (_gameMode === "humain") {
    document.getElementById("modal-title").textContent = "Les deux joueurs acceptent la nulle ?";
    btn.textContent = "Confirmer la nulle";
    btn.className   = "btn btn-reprendre";
    btn.onclick = () => { fermerModal(); sendAction({ type: "nulle_hh" }); };
  } else {
    document.getElementById("modal-title").textContent = "Proposer la nulle à Stockfish ?";
    btn.textContent = "Proposer la nulle";
    btn.className   = "btn";
    btn.onclick = () => { fermerModal(); sendAction({ type: "nulle" }); };
  }
  document.getElementById("modal-overlay").classList.add("open");
}

function ouvrirModalBackMenu() {
  const msg = _gameMode === "humain"
    ? "Quitter ? La partie en cours sera perdue."
    : "Quitter et revenir au menu ?";
  ouvrirModal("back_menu", msg, "Quitter", "");
}

function ouvrirModal(actionType, titre, labelConfirm, btnClass) {
  document.getElementById("modal-title").textContent = titre;
  const btn = document.getElementById("modal-confirm");
  btn.textContent = labelConfirm;
  btn.className = "btn " + (btnClass || "btn-reprendre");
  btn.onclick = () => { fermerModal(); sendAction({ type: actionType }); };
  // Toujours afficher les boutons standard (pas les boutons couleur)
  const std  = document.getElementById("modal-btns-standard");
  const coul = document.getElementById("modal-btns-couleur");
  if (std)  std.style.display  = "flex";
  if (coul) coul.style.display = "none";
  document.getElementById("modal-overlay").classList.add("open");
}

function fermerModal() {
  document.getElementById("modal-overlay").classList.remove("open");
}

// ── Actions ───────────────────────────────────────────────────────────────

function sendAction(data) {
  stopCountdown();
  socket.emit("action", data);

  if (data.type === "meilleur" && bestMove) {
    const [bFrom, bTo] = uciToCoords(bestMove);
    const [lFrom, lTo] = uciToCoords(lastMove);
    renderBoard(currentFen, lFrom, lTo, bFrom, bTo, null, null);
    document.getElementById("btn-best").disabled = true;
  } else if (data.type === "continuer") {
    hideFeedback();
  } else if (data.type === "reprendre") {
    // Retirer le coup annulé de tous les historiques
    if (reviewFens.length > 1)  reviewFens.pop();
    if (reviewMoves.length > 0) reviewMoves.pop();
    reviewIdx = Math.max(0, reviewFens.length - 1);
    _pendingMove = null;  // éviter double entrée si qualite arrive après
    _renderHistory();
    // Revenir au FEN d'avant le coup annulé
    currentFen = reviewFens[reviewIdx] || currentFen;
    lastMove = null;
    renderBoard(currentFen, null, null, null, null, null, null);
    // Message d'instruction dans turn-info
    const turnInfo = document.getElementById("turn-info");
    if (turnInfo) {
      turnInfo.textContent = "Replacez toutes les pièces impliquées par votre coup";
      turnInfo.className = "";
    }
    hideFeedback();
  }
}

// ── Material ──────────────────────────────────────────────────────────────

function updateMaterial(fen) {
  const vals  = { P:1,N:3,B:3,R:5,Q:9, p:1,n:3,b:3,r:5,q:9 };
  const initW = { P:8,N:2,B:2,R:2,Q:1 };
  const initB = { p:8,n:2,b:2,r:2,q:1 };
  const symW  = { P:'wP',N:'wN',B:'wB',R:'wR',Q:'wQ' };
  const symB  = { p:'bP',n:'bN',b:'bB',r:'bR',q:'bQ' };

  const present = {};
  for (const ch of fen.split(' ')[0])
    if (ch in vals) present[ch] = (present[ch] || 0) + 1;

  let scoreW = 0, scoreB = 0;
  for (const [p, n] of Object.entries(present))
    p === p.toUpperCase() ? scoreW += vals[p] * n : scoreB += vals[p] * n;
  const diff = scoreW - scoreB;

  let topHtml = '', botHtml = '';
  for (const [p, init] of Object.entries(initW)) {
    const cap = init - (present[p] || 0);
    const img = `<img src="/static/pieces/${symW[p]}.svg" style="width:18px;height:18px;">`;
    for (let i = 0; i < cap; i++) topHtml += img;
  }
  if (diff < 0) topHtml += `<span class="mat-score">+${Math.abs(diff)}</span>`;

  for (const [p, init] of Object.entries(initB)) {
    const cap = init - (present[p] || 0);
    const img = `<img src="/static/pieces/${symB[p]}.svg" style="width:18px;height:18px;">`;
    for (let i = 0; i < cap; i++) botHtml += img;
  }
  if (diff > 0) botHtml += `<span class="mat-score">+${diff}</span>`;

  document.getElementById('material-top').innerHTML    = topHtml || '&nbsp;';
  document.getElementById('material-bottom').innerHTML = botHtml || '&nbsp;';
}

// ── Review ────────────────────────────────────────────────────────────────
let reviewFens   = [];
let reviewMoves  = [];
let reviewIdx    = 0;
let _isAnalysed  = false;   // true après analyse_terminee
let _autoPlayTimer = null;  // setInterval handle
let _gameSource  = "externe"; // "niclink" ou "externe"

function reviewPrev() {
  if (reviewIdx > 0) { reviewIdx--; renderReview(); }
}
function reviewNext() {
  if (reviewIdx < reviewFens.length - 1) { reviewIdx++; renderReview(); }
}

function reviewGoTo(index) {
  const panelPause = document.getElementById("panel-pause");
  if (panelPause && panelPause.style.display !== "none") {
    if (index >= 0 && index < _pauseReviewFens.length) {
      _pauseReviewIdx = index;
      _renderPauseReview();
    }
    return;
  }
  if (index >= 0 && index < reviewFens.length) {
    reviewIdx = index;
    renderReview();
  }
}

// ── Autoplay ─────────────────────────────────────────────────────────────

function _setAutoPlayIcon(playing) {
  const icon = document.getElementById("btn-autoplay-icon");
  if (!icon) return;
  if (playing) {
    // Icône pause : deux rectangles
    icon.innerHTML = '<rect x="5" y="4" width="4" height="16"/><rect x="15" y="4" width="4" height="16"/>';
  } else {
    // Icône play : triangle
    icon.innerHTML = '<polygon points="6,4 20,12 6,20"/>';
  }
}

// ── Config Humain vs Humain ──────────────────────────────────────────────

let _hhColor  = "white";
let _gameMode = "pedagogique";  // "pedagogique" ou "humain"

function selectColorHH(c) {
  _hhColor = c;
  // Sync checkbox si appelé programmatiquement
  const chk = document.getElementById("hh-random");
  if (chk) chk.checked = (c === "random");
  // Changer les labels selon le mode
  const lblWhite = document.getElementById("label-white-name");
  const lblBlack = document.getElementById("label-black-name");
  if (c === "random") {
    if (lblWhite) lblWhite.textContent = "Joueur 1";
    if (lblBlack) lblBlack.textContent = "Joueur 2";
  } else {
    if (lblWhite) lblWhite.textContent = "Joueur Blancs";
    if (lblBlack) lblBlack.textContent = "Joueur Noirs";
  }
}

function startGameHH() {
  const white = document.getElementById("cfg-white-name")?.value.trim() || "Anonyme1";
  const black = document.getElementById("cfg-black-name")?.value.trim() || "Anonyme2";
  const type  = document.getElementById("cfg-hh-type")?.value || "serieuse";
  sendAction({ type: "start_humain", white, black, color: _hhColor, game_type: type });
}

function _stopAutoPlay() {
  if (_autoPlayTimer) { clearInterval(_autoPlayTimer); _autoPlayTimer = null; }
  _setAutoPlayIcon(false);
}

function _setNavControls(enabled) {
  ["btn-autoplay", "autoplay-speed", "btn-review-prev", "btn-review-next"].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = !enabled;
    el.style.opacity = enabled ? "1" : "0.4";
    el.style.pointerEvents = enabled ? "" : "none";
  });
}

function toggleAutoPlay() {
  if (_autoPlayTimer) {
    _stopAutoPlay();
    return;
  }
  const btn    = document.getElementById("btn-autoplay");
  const slider = document.getElementById("autoplay-speed");
  const delay  = slider ? parseFloat(slider.value) * 1000 : 2000; // gauche=0.2s rapide, droite=5s lent
  _setAutoPlayIcon(true);
  _autoPlayTimer = setInterval(() => {
    if (reviewIdx < reviewFens.length - 1) {
      reviewIdx++;
      renderReview();
    } else {
      _stopAutoPlay();
    }
  }, delay);
}

// ── Symbole qualité sur l'échiquier (style Lichess) ──────────────────────

const QUALITE_GLYPH = {
  "bon":         { sym: "✓",  bg: "#5d8f3f", fg: "#fff" },
  "imprecision": { sym: "?!", bg: "#e6a117", fg: "#fff" },
  "erreur":      { sym: "?",  bg: "#d44b1a", fg: "#fff" },
  "blunder":     { sym: "??", bg: "#8b0086", fg: "#fff" },
};

function showQualiteGlyph(squareId, qualite) {
  const sq = document.getElementById("sq-" + squareId);
  if (!sq) return;
  removeQualiteGlyph();
  const g = QUALITE_GLYPH[qualite];
  if (!g) return;
  const badge = document.createElement("div");
  badge.id = "qualite-glyph";
  badge.style.position     = "absolute";
  badge.style.top          = "2px";
  badge.style.right        = "2px";
  badge.style.width        = "38%";
  badge.style.height       = "38%";
  badge.style.borderRadius = "50%";
  badge.style.background   = g.bg;
  badge.style.color        = g.fg;
  badge.style.display      = "flex";
  badge.style.alignItems   = "center";
  badge.style.justifyContent = "center";
  badge.style.fontSize     = "clamp(7px, 1.8cqw, 13px)";
  badge.style.fontWeight   = "bold";
  badge.style.lineHeight   = "1";
  badge.style.pointerEvents = "none";
  badge.style.zIndex       = "10";
  badge.style.boxShadow    = "0 1px 4px rgba(0,0,0,0.6)";
  badge.style.letterSpacing = "-0.5px";
  badge.textContent = g.sym;
  sq.appendChild(badge);
}

function removeQualiteGlyph() {
  const old = document.getElementById("qualite-glyph");
  if (old) old.remove();
}

function showReviewBestMove() {
  if (reviewIdx === 0 || !_isAnalysed) return;
  const m = reviewMoves[reviewIdx - 1];
  if (!m || !m.best_move) return;
  // Afficher la flèche meilleur coup sur l'échiquier
  const [lFrom, lTo] = uciToCoords(m.uci || "");
  const [bFrom, bTo] = uciToCoords(m.best_move);
  renderBoard(reviewFens[reviewIdx], lFrom, lTo, bFrom, bTo, null, null);
  // Afficher le SAN du meilleur coup si disponible
  const sanEl = document.getElementById("review-best-move-san");
  if (sanEl) {
    sanEl.textContent = m.best_move;
    sanEl.style.display = "block";
  }
}

function _updateReviewBestMoveBtn() {
  const row = document.getElementById("review-best-move-row");
  const sanEl = document.getElementById("review-best-move-san");
  if (!row) return;
  if (sanEl) { sanEl.style.display = "none"; sanEl.textContent = ""; }
  if (!_isAnalysed || reviewIdx === 0) {
    row.style.display = "none";
    return;
  }
  const m = reviewMoves[reviewIdx - 1];
  const hasBest = m && m.best_move && m.best_move !== (m.uci || "");
  row.style.display = hasBest ? "block" : "none";
}

// Rendu de l'historique cliquable (utilisé par renderReview et _renderPauseReview)
function renderHistory(activeIdx) {
  const histEl = document.getElementById("historique");
  if (!histEl) return;
  // Séparer par color pour être robuste (HH et pédagogique)
  const whites = reviewMoves.map((m, i) => ({...m, _idx: i + 1})).filter(m => m.color === "white");
  const blacks = reviewMoves.map((m, i) => ({...m, _idx: i + 1})).filter(m => m.color === "black");
  const total  = Math.max(whites.length, blacks.length);
  let html = '<table style="width:100%;border-collapse:collapse;">';
  html += '<tr><th style="color:#888;font-weight:normal;padding:2px 4px;">Blancs</th><th style="color:#888;font-weight:normal;padding:2px 4px;">Noirs</th></tr>';
  for (let i = 0; i < total; i++) {
      const mw   = whites[i];
      const mb   = blacks[i];
      const idxW = mw ? mw._idx : -1;
      const idxB = mb ? mb._idx : -1;
      const activeW = activeIdx === idxW ? "font-weight:bold;" : "";
      const activeB = activeIdx === idxB ? "font-weight:bold;" : "";
      const colorW  = activeIdx === idxW ? "#e94560" : qualiteColor(mw ? mw.qualite : "bon");
      const colorB  = activeIdx === idxB ? "#e94560" : qualiteColor(mb ? mb.qualite : "bon");
      html += `<tr>`;
      html += mw ? `<td style="padding:2px 4px;cursor:pointer;color:${colorW};${activeW}" onclick="reviewGoTo(${idxW})">${i+1}. ${mw.san}${qualiteSymbole(mw.qualite)}</td>` : `<td></td>`;
      html += mb ? `<td style="padding:2px 4px;cursor:pointer;color:${colorB};${activeB}" onclick="reviewGoTo(${idxB})">${mb.san}${qualiteSymbole(mb.qualite)}</td>` : `<td></td>`;
      html += `</tr>`;
  }
  html += '</table>';
  histEl.innerHTML = html;
}

function renderReview() {
  const fen = reviewFens[reviewIdx];
  let from = null, to = null, toSquare = null;
  if (reviewIdx > 0) {
    const m = reviewMoves[reviewIdx - 1];
    if (m && m.uci) {
      [from, to] = uciToCoords(m.uci);
      toSquare = to;
    }
  }
  renderBoard(fen, from, to, null, null, null, null);

  // Afficher le symbole qualité sur la case de destination si partie analysée
  removeQualiteGlyph();
  if (_isAnalysed && reviewIdx > 0 && toSquare) {
    const m = reviewMoves[reviewIdx - 1];
    if (m && m.qualite && m.qualite !== "bon") {
      showQualiteGlyph(toSquare, m.qualite);
    }
  }

  const moveInfo = document.getElementById("review-move-info");
  const moveSan  = document.getElementById("review-move-san");
  if (reviewIdx === 0) {
    if (moveInfo) moveInfo.textContent = "Position initiale";
    if (moveSan)  moveSan.textContent  = "";
  } else {
    const m = reviewMoves[reviewIdx - 1];
    if (moveInfo) moveInfo.textContent = `Coup ${reviewIdx}`;
    if (moveSan)  moveSan.textContent  = m ? m.san : "";
  }
  renderHistory(reviewIdx);
  _updateReviewBestMoveBtn();
}

// ── Import PGN ────────────────────────────────────────────────────────────

function loadPgnFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    parsePgn(e.target.result);
  };
  reader.readAsText(file);
}

function parsePgn(pgn) {
  try {
    const chess = new Chess();
    if (!chess.load_pgn(pgn)) {
      alert("PGN invalide ou non reconnu.");
      return;
    }
    // Extraire les métadonnées
    const white  = chess.header().White  || "Blancs";
    const black  = chess.header().Black  || "Noirs";
    const result = chess.header().Result || "*";
    // Reconstruire les FEN et la liste des coups
    const history = chess.history({ verbose: true });
    const chess2  = new Chess();
    const fens    = [chess2.fen().split(" ")[0]];
    const moves   = [];
   // Extraire les commentaires depuis le PGN brut
    const commentRegex = /\{([^}]*)\}/g;
    const allComments = [];
    let cm;
    while ((cm = commentRegex.exec(pgn)) !== null) {
      allComments.push(cm[1].trim());
    }

    for (let i = 0; i < history.length; i++) {
      const m = history[i];
      const comment = allComments[i] || "";
      // Lire la qualité depuis le commentaire NicLink
      let qualite = "bon";
      if (comment.includes("!!") || comment.toLowerCase().includes("blunder")) qualite = "blunder";
      else if (comment.includes("!") || comment.toLowerCase().includes("erreur")) qualite = "erreur";
      else if (comment.includes("?") || comment.toLowerCase().includes("imprecision")) qualite = "imprecision";
      moves.push({ san: m.san, uci: m.from + m.to + (m.promotion || ""), color: m.color === "w" ? "white" : "black", qualite });
      chess2.move(m);
      fens.push(chess2.fen().split(" ")[0]);
    }
    // Peupler la révision
    reviewFens  = fens;
    reviewMoves = moves;
    reviewIdx   = fens.length - 1;
    // Détecter si la partie est déjà analysée (au moins un coup non-"bon")
    _isAnalysed = moves.some(m => m.qualite && m.qualite !== "bon");
    // Afficher les noms
    document.getElementById("player-top-name").textContent    = black;
    document.getElementById("player-bottom-name").textContent = white;
    document.getElementById("gameover-title").textContent  = "Révision PGN";
    document.getElementById("gameover-result").textContent = result;
    document.getElementById("rv-game-info").textContent    = `${white} vs ${black}`;
    _setNavControls(true);
    renderReview();
    _updateActionButtons();

    // Bouton Analyser
    const btnAnalyse = document.getElementById("btn-analyser");
    if (btnAnalyse) {
      const dejaAnalyse = allComments.length === history.length && allComments.some(c => c.includes("cp"));
      btnAnalyse.style.display = dejaAnalyse ? "none" : "inline-block";
      btnAnalyse.textContent = "🔍 Analyser la partie";
      btnAnalyse.disabled = false;
      btnAnalyse._movesUci = moves.map(m => m.uci);
    }
    const btnVider = document.getElementById("btn-vider-analyse");
    if (btnVider) btnVider.style.display = "inline-block";
  } catch(e) {
    alert("Erreur lors du parsing PGN : " + e.message);
  }
}
// ── Pause ──────────────────────────────────────────────────────────────────

let _pauseReviewFens    = [];
let _pauseReviewMoves   = [];
let _pauseReviewIdx     = 0;
let _pauseChangerCouleur = false;  // toggle local pendant la pause

// ── Rendu échiquier avec cases en erreur ──────────────────────────────────
function renderBoardWithErrors(expectedFen, physicalFen) {
  // Afficher la position attendue (pièces correctes à 100%)
  renderBoard(expectedFen, null, null, null, null, null, null);
  if (!physicalFen || physicalFen === expectedFen) return;
  const expected = fenToBoard(expectedFen);
  const physical = fenToBoard(physicalFen);
  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const id  = `${file}-${rank}`;
      const sq  = document.getElementById(`sq-${id}`);
      if (!sq) continue;
      const expPiece = expected[id] || null;
      const phyPiece = physical[id] || null;
      if (expPiece !== phyPiece) {
        // Case en erreur : fond rouge translucide
        // La pièce attendue est déjà affichée par renderBoard à 100% d'opacité
        // Si la case doit être vide (expPiece null), on la vide
        sq.classList.add("sq-error");
        if (!expPiece) sq.innerHTML = "";
      }
    }
  }
}

socket.on("game_folders", (data) => {
  // data.folders = [{ mode: "Stockfish", type: "Pedagogique" }, ...]
  const sel = document.getElementById("save-type");
  if (!sel || !data.folders) return;
  // Regrouper par mode
  const groups = {};
  for (const f of data.folders) {
    if (!groups[f.mode]) groups[f.mode] = [];
    groups[f.mode].push(f.type);
  }
  sel.innerHTML = "";
  for (const [mode, types] of Object.entries(groups)) {
    const og = document.createElement("optgroup");
    og.label = `── ${mode} ──`;
    for (const type of types) {
      const opt = document.createElement("option");
      opt.value = `${mode}-${type}`;
      opt.textContent = `${mode} — ${type}`;
      og.appendChild(opt);
    }
    sel.appendChild(og);
  }
});

socket.on("position_error", (data) => {
  renderBoardWithErrors(data.expected_fen, data.physical_fen);
});

socket.on("position_ok", (data) => {
  // Nettoyer les cases rouges : renderBoard normal
  renderBoard(data.fen, null, null, null, null, null, null);
});

socket.on("illegal_position", (data) => {
  const turnInfo = document.getElementById("turn-info");
  if (turnInfo) {
    turnInfo.textContent = data.message || "⚠ Position illégale";
    turnInfo.className = "warning";
  }
});

socket.on("resume", (data) => {
  // Réinitialiser l'historique au point de reprise (historique tronqué)
  reviewFens  = data.history_fen   || [];
  reviewMoves = data.history_moves || [];
  reviewIdx   = Math.max(0, reviewFens.length - 1);
  if (reviewFens.length > 0) _setNavControls(true);
  // Réinitialiser aussi _histMoves (panel historique gauche)
  _histMoves = [];
  for (const m of reviewMoves) {
    _histMoves.push({ san: m.san, qualite: m.qualite || "bon", color: m.color || "white" });
  }
  _renderHistory();
  _pendingMove = null;
});

socket.on("pause", (data) => {
  const player = data.player || "Joueur";
  const color  = data.playing_white ? "Blancs" : "Noirs";

  // Stocker les infos du coup pour la séquence punitive
  if (data.best_move) bestMove = data.best_move;
  if (data.punishment_line) _punishmentLine = data.punishment_line;
  if (data.fen_avant_coup)  _fenAvantCoup   = data.fen_avant_coup;

  // ── Info joueur ──
  const el = document.getElementById("pause-info");
  if (el) el.textContent = `${player} joue les ${color}`;

  // ── Feedback du coup (pause auto) ──
  const feedbackBox   = document.getElementById("pause-feedback-box");
  const feedbackLabel = document.getElementById("pause-feedback-label");
  const feedbackDetail= document.getElementById("pause-feedback-detail");
  if (feedbackBox) {
    if (data.auto && data.qualite) {
      const LABELS = { bon:"✓ Bon coup", imprecision:"?! Imprécision", erreur:"? Erreur", blunder:"?? Gaffe" };
      feedbackBox.style.display  = "block";
      feedbackBox.className      = "feedback-box-pause " + data.qualite;
      if (feedbackLabel)  feedbackLabel.textContent  = LABELS[data.qualite] || data.qualite;
      if (feedbackDetail) feedbackDetail.textContent = data.san ? `${data.san} — ${data.delta_cp}cp de perte` : "";
    } else {
      feedbackBox.style.display = "none";
    }
  }

  // ── Boutons contextuels ──
  const btnReprendre = document.getElementById("btn-pause-reprendre");
  const btnContinuer = document.getElementById("btn-pause-continuer");
  const btnMeilleur  = document.getElementById("btn-pause-meilleur");
  const btnSequence  = document.getElementById("btn-pause-sequence");

  // Reprendre : seulement si pause auto (un coup a été joué)
  if (btnReprendre) {
    btnReprendre.style.display = data.auto ? "block" : "none";
  }
  // Continuer : seulement si pause auto
  if (btnContinuer) {
    btnContinuer.style.display = data.auto ? "block" : "none";
  }
  // Meilleur coup : si best_move disponible
  if (btnMeilleur) {
    const hasBest = !!data.best_move;
    btnMeilleur.disabled = !hasBest;
    btnMeilleur.style.opacity = hasBest ? "1" : "0.4";
  }
  // Séquence punitive : si punishment_line disponible (pause auto seulement)
  if (btnSequence) {
    const hasSeq = data.auto && data.punishment_line && data.punishment_line.length > 0;
    btnSequence.style.display = data.auto ? "block" : "none";
    btnSequence.disabled = !hasSeq;
    btnSequence.style.opacity = hasSeq ? "1" : "0.4";
  }

  // Reset toggle changer_couleur
  _pauseChangerCouleur = false;
  _updateChangerCouleurBtn();

  // Initialiser la navigation avec l'historique courant
  _pauseReviewFens  = reviewFens.slice();
  _pauseReviewMoves = reviewMoves.slice();
  _pauseReviewIdx   = _pauseReviewFens.length - 1;
  _renderPauseReview();
});

socket.on("pause_wait_position", (data) => {
  // Afficher la position cible + cases en erreur
  renderBoardWithErrors(data.fen, data.physical_fen || null);
});

function _renderPauseReview() {
  const fen = _pauseReviewFens[_pauseReviewIdx];
  if (!fen) return;
  let from = null, to = null;
  const m = _pauseReviewIdx > 0 ? _pauseReviewMoves[_pauseReviewIdx - 1] : null;
  if (m && m.uci) [from, to] = uciToCoords(m.uci);
  renderBoard(fen, from, to, null, null, null, null);
  // Historique cliquable avec le coup courant surligné
  renderHistory(_pauseReviewIdx);
  // SAN du coup courant dans le panneau Navigation
  const sanEl = document.getElementById("pause-move-san");
  if (sanEl) sanEl.textContent = (_pauseReviewIdx === 0) ? "" : (m ? m.san : "");
}

function pauseReviewPrev() {
  if (_pauseReviewIdx > 0) { _pauseReviewIdx--; _renderPauseReview(); }
}

function pauseReviewNext() {
  if (_pauseReviewIdx < _pauseReviewFens.length - 1) { _pauseReviewIdx++; _renderPauseReview(); }
}

// ── Pause : changer couleur (toggle local) + reprendre ───────────────────

function _updateChangerCouleurBtn() {
  const btn = document.getElementById("btn-changer-couleur");
  if (!btn) return;
  if (_pauseChangerCouleur) {
    btn.style.background = "#e94560";
    btn.style.borderColor = "#e94560";
    btn.style.color = "#fff";
    btn.textContent = "🔄 Annuler changement";
  } else {
    btn.style.background  = "#0f3460";
    btn.style.borderColor = "#e94560";
    btn.style.color       = "#e0e0e0";
    btn.textContent = "🔄 Changer de couleur";
  }
}

function pauseToggleChangerCouleur() {
  _pauseChangerCouleur = !_pauseChangerCouleur;
  _updateChangerCouleurBtn();
  // Mise à jour visuelle des noms joueurs (swap_color simulé localement)
  const topName = document.getElementById("player-top-name");
  const botName = document.getElementById("player-bottom-name");
  if (!topName || !botName) return;
  // On inverse les noms/couleurs actuels
  const tmpText  = topName.textContent;
  const tmpColor = topName.style.color;
  topName.textContent = botName.textContent;
  topName.style.color = botName.style.color;
  botName.textContent = tmpText;
  botName.style.color = tmpColor;
}

function pauseReprendre() {
  const fen = _pauseReviewFens[_pauseReviewIdx] || null;
  sendAction({
    type:            "reprendre",
    changer_couleur: _pauseChangerCouleur,
    fen:             fen,
  });
}

// ── Init ──────────────────────────────────────────────────────────────────
socket.on("analyse_coup", (data) => {
  if (reviewMoves[data.index]) {
    reviewMoves[data.index].qualite   = data.qualite;
    reviewMoves[data.index].delta_cp  = data.delta_cp;
    reviewMoves[data.index].best_move = data.best_move;
  }

  // Barre de progression
  const btn = document.getElementById("btn-analyser");
  if (btn) {
    const pct = Math.round((data.index + 1) / data.total * 100);
    btn.textContent = `⏳ Analyse... ${pct}%`;
    btn.style.background = `linear-gradient(to right, #4a4a8a ${pct}%, #2a2a4a ${pct}%)`;
  }
  renderReview();
});

socket.on("analyse_terminee", (data) => {
  _isAnalysed = true;
  const btn = document.getElementById("btn-analyser");
  if (btn) { btn.textContent = "✓ Analysé"; btn.disabled = true; }
  _updateActionButtons();
});

buildBoard();
_buildBoardPosInit();
renderBoard(currentFen, null, null, null, null, null, null);
// Griser les contrôles nav au démarrage (pas de partie chargée)
_setNavControls(false);
