// ── Constantes ────────────────────────────────────────────────────────────
let _boardFlipped = false;  // true = noirs en bas

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
  const ranks = _boardFlipped ? [0,1,2,3,4,5,6,7] : [7,6,5,4,3,2,1,0];
  ranks.forEach(r => {
    const s = document.createElement("span");
    s.textContent = r + 1;
    rankCoord.appendChild(s);
  });
  const fileCoord = document.getElementById("coord-file");
  fileCoord.innerHTML = "";
  const files = _boardFlipped ? "hgfedcba".split("") : "abcdefgh".split("");
  files.forEach(f => {
    const s = document.createElement("span");
    s.textContent = f;
    fileCoord.appendChild(s);
  });

  const rankOrder = _boardFlipped ? [0,1,2,3,4,5,6,7] : [7,6,5,4,3,2,1,0];
  const fileOrder = _boardFlipped ? [7,6,5,4,3,2,1,0] : [0,1,2,3,4,5,6,7];
  for (const rank of rankOrder) {
    for (const file of fileOrder) {
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
  const sel = document.getElementById("rv-seq-moves");
  const seqMoves = sel ? parseInt(sel.value) : 3;
  btn.textContent = "⏳ Analyse en cours...";
  btn.disabled = true;
  socket.emit("analyser_pgn", { moves: btn._movesUci, niveau: 20, seq_moves: seqMoves });
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

// ── Flip échiquier ────────────────────────────────────────────────────────

function flipBoard() {
  _boardFlipped = !_boardFlipped;
  buildBoard();
  // Mettre à jour le titre du bouton
  const btn = document.getElementById("btn-flip");
  if (btn) btn.title = _boardFlipped ? "Blancs en bas" : "Noirs en bas";
  // Inverser les noms et matériaux
  const topName  = document.getElementById("player-top-name");
  const botName  = document.getElementById("player-bottom-name");
  const topMat   = document.getElementById("material-top");
  const botMat   = document.getElementById("material-bottom");
  if (topName && botName) {
    const tmp = topName.textContent; topName.textContent = botName.textContent; botName.textContent = tmp;
    const tmpC = topName.style.color; topName.style.color = botName.style.color; botName.style.color = tmpC;
  }
  // material est géré par updateMaterial() qui tient compte de _boardFlipped
  // Re-rendre la position courante
  const fen = currentFen || "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR";
  renderBoard(fen, null, null, null, null, null, null);
}

// ── Échiquier review ──────────────────────────────────────────────────────


function buildBoardReview() {
  const board = document.getElementById("board");
  if (!board) return;
  board.innerHTML = "";
  const rankOrder = _boardFlipped ? [0,1,2,3,4,5,6,7] : [7,6,5,4,3,2,1,0];
  const fileOrder = _boardFlipped ? [7,6,5,4,3,2,1,0] : [0,1,2,3,4,5,6,7];
  for (const rank of rankOrder) {
    for (const file of fileOrder) {
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
  document.getElementById("screen-menu").style.display                  = data.state === "menu"                  ? "flex" : "none";
  document.getElementById("screen-config").style.display                = data.state === "config"                ? "flex" : "none";
  document.getElementById("screen-config-humain").style.display         = data.state === "config_humain"         ? "flex" : "none";

  const laboEl = document.getElementById("screen-labo");
  if (laboEl) laboEl.style.display = data.state === "labo" ? "grid" : "none";

  // Exercices
  const exSelEl = document.getElementById("screen-exercices");
  if (exSelEl) exSelEl.style.display = data.state === "exercices" ? "flex" : "none";
  const exRunEl = document.getElementById("screen-exercice-running");
  if (exRunEl) exRunEl.style.display = data.state === "exercice_running" ? "grid" : "none";

  if (data.state === "exercices" && data.ouvertures) {
    exRenderOuvertures(data.ouvertures);
  }
  // Quand on entre dans le labo, réinitialiser la position virtuelle
  if (data.state === "labo") {
    _laboVirtualFen = "";
    const copyBtn = document.getElementById("labo-btn-copy");
    if (copyBtn) copyBtn.style.display = "none";
  }
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
    // Assigner _movesUci au bouton analyser pour les parties NicLink (HH ou péda)
    const btnA2 = document.getElementById("btn-analyser");
    if (btnA2 && reviewMoves.length > 0) {
      btnA2._movesUci = reviewMoves.map(m => m.uci).filter(Boolean);
    }
    _updateActionButtons();
  }
  if (data.state === "menu") {
    _gameSource = "externe";
    _viderAnalyse();
    // Vider les champs de config HH
    const wName = document.getElementById("cfg-white-name");
    const bName = document.getElementById("cfg-black-name");
    if (wName) wName.value = "";
    if (bName) bName.value = "";
    // Remettre l'échiquier dans le sens normal
    if (_boardFlipped) { _boardFlipped = false; buildBoard(); }
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
  const seqRow   = document.getElementById("rv-seq-row");
  const saveBlock = document.getElementById("card-save-block");
  const hasGame  = reviewFens.length > 1;
  if (btnA)   btnA.style.display   = (hasGame && !_isAnalysed) ? "inline-block" : "none";
  if (seqRow) seqRow.style.display = (hasGame && !_isAnalysed) ? "flex" : "none";
  if (btnD)   btnD.style.display   = _isAnalysed ? "inline-block" : "none";
  if (btnV)   btnV.style.display   = hasGame ? "inline-block" : "none";
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

  if (_boardFlipped) {
    document.getElementById('material-top').innerHTML    = botHtml || '&nbsp;';
    document.getElementById('material-bottom').innerHTML = topHtml || '&nbsp;';
  } else {
    document.getElementById('material-top').innerHTML    = topHtml || '&nbsp;';
    document.getElementById('material-bottom').innerHTML = botHtml || '&nbsp;';
  }
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
  const hasSeqRv = m && m.punishment_line && m.punishment_line.length > 0;
  const btnSeqRv = document.getElementById("btn-rv-sequence");
  if (btnSeqRv) {
    btnSeqRv.style.display = hasSeqRv ? "block" : "none";
    btnSeqRv.disabled = !hasSeqRv;
  }
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
  const laboScreen = document.getElementById("screen-labo");
  if (laboScreen && laboScreen.style.display !== "none") {
    // En mode labo : afficher les erreurs sur labo-board
    laboRenderBoardWithErrors(data.expected_fen, data.physical_fen);
  } else {
    renderBoardWithErrors(data.expected_fen, data.physical_fen);
  }
});

function laboRenderBoardWithErrors(expectedFen, physicalFen) {
  laboRenderBoard(expectedFen, null, null);
  if (!physicalFen || physicalFen === expectedFen) return;
  const expected = fenToBoard(expectedFen);
  const physical = fenToBoard(physicalFen);
  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const id = `${file}-${rank}`;
      const sq = document.getElementById(`labo-sq-${id}`);
      if (!sq) continue;
      if ((expected[id] || null) !== (physical[id] || null)) {
        sq.classList.add("sq-error");
        if (!expected[id]) sq.innerHTML = "";
      }
    }
  }
}

let _laboCopyMode = false; // true pendant la copie source virtuelle → plateau

socket.on("position_ok", (data) => {
  const exScreen = document.getElementById("screen-exercice-running");
  if (exScreen && exScreen.style.display !== "none") {
    exRenderBoard(data.fen, null, null);
    // Réactiver le bouton sync après chaque coup adversaire placé
    exSetSyncBtn(true);
    return;
  }
  const laboScreen = document.getElementById("screen-labo");
  if (laboScreen && laboScreen.style.display !== "none") {
    laboRenderBoard(data.fen, null, null);
    if (_laboCopyMode) {
      const turnEl = document.getElementById("labo-turn-info");
      if (turnEl) { turnEl.textContent = "✓ Position reproduite"; turnEl.style.color = "#4caf50"; }
      _laboCopyMode = false;
    }
  } else {
    renderBoard(data.fen, null, null, null, null, null, null);
  }
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
    reviewMoves[data.index].qualite          = data.qualite;
    reviewMoves[data.index].delta_cp         = data.delta_cp;
    reviewMoves[data.index].best_move        = data.best_move;
    reviewMoves[data.index].punishment_line  = data.punishment_line || [];
    reviewMoves[data.index].fen_avant_coup   = data.fen_avant_coup  || null;
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

// ── Séquence review ──────────────────────────────────────────────────────────

function jouerSequenceReview() {
  const m = reviewMoves[reviewIdx - 1];
  if (!m || !m.punishment_line || m.punishment_line.length === 0 || !m.fen_avant_coup) return;

  const btnSeq = document.getElementById("btn-rv-sequence");
  if (btnSeq) btnSeq.disabled = true;

  // Construire la liste des FENs à animer
  const fens = [];
  try {
    const game = new Chess(m.fen_avant_coup);
    // Rejouer le coup humain
    if (m.uci) {
      game.move({ from: m.uci.slice(0,2), to: m.uci.slice(2,4),
                  promotion: m.uci.length === 5 ? m.uci[4] : undefined });
    }
    fens.push(game.fen().split(" ")[0]);
    // Puis la séquence punitive
    for (const uci of m.punishment_line) {
      const ok = game.move({ from: uci.slice(0,2), to: uci.slice(2,4),
                              promotion: uci.length === 5 ? uci[4] : undefined });
      if (!ok) break;
      fens.push(game.fen().split(" ")[0]);
    }
  } catch(e) {
    console.error("jouerSequenceReview erreur:", e);
    if (btnSeq) btnSeq.disabled = false;
    return;
  }

  // Animer
  const ucis = [m.uci, ...m.punishment_line];
  let idx = 0;
  const baseFen = reviewFens[reviewIdx] || fens[0];
  function step() {
    if (idx >= fens.length) {
      setTimeout(() => {
        renderReview();
        if (btnSeq) btnSeq.disabled = false;
      }, 1500);
      return;
    }
    const fen = fens[idx];
    const uci = ucis[idx] || null;
    const [from, to] = uci ? uciToCoords(uci) : [null, null];
    renderBoard(fen, from, to, null, null, null, null);
    idx++;
    setTimeout(step, 1000);
  }
  step();
}

// ── Labo config ───────────────────────────────────────────────────────────────

let _laboEngine  = "stockfish";
let _laboColor   = "white";
let _laboPgnFens  = [];
let _laboPgnMoves = [];
let _laboPgnIdx   = 0;
let _laboVirtualFen = ""; // FEN de la position virtuelle courante

function laboSelectEngine(e) {
  _laboEngine = e;
  ["sf","maia","rodent"].forEach(x => {
    document.getElementById(`labo-eng-${x}`)?.classList.toggle("selected", x === (e==="stockfish"?"sf":e));
  });
  document.getElementById("labo-cfg-sf").style.display     = e === "stockfish" ? "" : "none";
  document.getElementById("labo-cfg-maia").style.display   = e === "maia"      ? "" : "none";
  document.getElementById("labo-cfg-rodent").style.display = e === "rodent"    ? "" : "none";
  laboPushConfig();
}



function laboAdjElo(delta) {
  const input = document.getElementById("labo-elo");
  let val = Math.max(1320, Math.min(3190, parseInt(input.value) + delta));
  input.value = val;
  document.getElementById("labo-elo-label").textContent = `~${val} Elo`;
  laboPushConfig();
}
function laboClampElo() {
  const input = document.getElementById("labo-elo");
  let val = parseInt(input.value);
  if (!isNaN(val)) { val = Math.max(1320, Math.min(3190, val)); input.value = val; laboPushConfig(); }
}
function laboAdjRodentElo(delta) {
  const input = document.getElementById("labo-rodent-elo");
  let val = Math.max(800, Math.min(2800, parseInt(input.value) + delta));
  input.value = val;
  document.getElementById("labo-rodent-elo-label").textContent = `${val} Elo`;
  laboPushConfig();
}
function laboClampRodentElo() {
  const input = document.getElementById("labo-rodent-elo");
  let val = parseInt(input.value);
  if (!isNaN(val)) { val = Math.max(800, Math.min(2800, val)); input.value = val; laboPushConfig(); }
}

function laboPushConfig() {
  sendAction({
    type:        "labo_set_config",
    engine_type: _laboEngine,
    human_color: _laboCamp,
    engine_elo:  parseInt(document.getElementById("labo-elo")?.value) || 1500,
    maia_elo:    parseInt(document.getElementById("labo-maia-elo")?.value) || 1500,
    rodent_elo:  parseInt(document.getElementById("labo-rodent-elo")?.value) || 800,
    analyse:     document.getElementById("labo-analyse-chk")?.checked !== false,
  });
  // Mettre à jour le label moteur
  const label = _laboEngine === "maia" ? `Maia ${document.getElementById("labo-maia-elo")?.value||1500}`
              : _laboEngine === "rodent" ? `Rodent ${document.getElementById("labo-rodent-elo")?.value||800}`
              : `Stockfish ~${document.getElementById("labo-elo")?.value||1500}elo`;
  const el = document.getElementById("labo-engine-label");
  if (el) el.textContent = label;
}

// PGN import et navigation
function laboLoadPgn(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const chess = new Chess();
      if (!chess.load_pgn(e.target.result)) { afficherToast("PGN invalide", "warning"); return; }
      const history = chess.history({ verbose: true });
      const white   = chess.header().White || "Blancs";
      const black   = chess.header().Black || "Noirs";
      const chess2  = new Chess();
      _laboPgnFens  = [chess2.fen().split(" ")[0]];
      _laboPgnMoves = [];
      for (const m of history) {
        chess2.move(m);
        _laboPgnFens.push(chess2.fen().split(" ")[0]);
        _laboPgnMoves.push(m.san);
      }
      _laboPgnIdx = _laboPgnFens.length - 1;
      _laboVirtualFen = _laboPgnFens[_laboPgnIdx];
      laboShowVirtualFen();
      const nav = document.getElementById("labo-pgn-nav");
      if (nav) nav.style.display = "flex";
      const info = document.getElementById("labo-pgn-info");
      if (info) info.textContent = `${white} vs ${black} — ${history.length} coups`;
      const copyBtn = document.getElementById("labo-btn-copy");
      if (copyBtn) copyBtn.style.display = "block";
      // Remplir l'historique
      _laboRenderPgnHistory();
      laboJournalAdd("config", `📂 PGN : ${file.name} (${history.length} coups)`);
      // Afficher l'onglet PGN
      const tabPgn = document.getElementById("labo-tab-pgn");
      if (tabPgn) tabPgn.style.display = "inline-block";
      _laboRenderPgnLeft();
      afficherToast("PGN chargé", "success");
    } catch(err) { afficherToast("Erreur PGN : " + err.message, "warning"); }
  };
  reader.readAsText(file);
}

function _laboRenderPgnHistory() {
  const hist = document.getElementById("labo-historique");
  if (!hist || !_laboPgnMoves.length) return;
  const whites = _laboPgnMoves.filter((_, i) => i % 2 === 0);
  const blacks = _laboPgnMoves.filter((_, i) => i % 2 === 1);
  const total  = Math.max(whites.length, blacks.length);
  let html = '<table style="width:100%;border-collapse:collapse;font-size:0.8rem;">';
  html += '<tr><th style="color:#556;width:20px;text-align:right;padding-right:4px;"></th>';
  html += '<th style="color:#aaa;text-align:left;padding:2px 3px;">Blancs</th>';
  html += '<th style="color:#aaa;text-align:left;padding:2px 3px;">Noirs</th></tr>';
  for (let i = 0; i < total; i++) {
    const wIdx = i * 2;
    const bIdx = i * 2 + 1;
    const active = _laboPgnIdx - 1;
    const cwW = active === wIdx ? "color:#e94560;font-weight:bold;" : "color:#ccc;";
    const cwB = active === bIdx ? "color:#e94560;font-weight:bold;" : "color:#888;";
    html += `<tr><td style="color:#444;text-align:right;padding-right:4px;font-size:0.72rem;">${i+1}.</td>`;
    html += whites[i] ? `<td style="padding:1px 3px;cursor:pointer;${cwW}" onclick="laboPgnGoTo(${wIdx+1})">${whites[i]}</td>` : "<td></td>";
    html += blacks[i] ? `<td style="padding:1px 3px;cursor:pointer;${cwB}" onclick="laboPgnGoTo(${bIdx+1})">${blacks[i]}</td>` : "<td></td>";
    html += "</tr>";
  }
  html += "</table>";
  hist.innerHTML = html;
  hist.scrollTop = hist.scrollHeight;
}

function laboPgnGoTo(idx) {
  if (idx < 0 || idx >= _laboPgnFens.length) return;
  _laboPgnIdx = idx;
  _laboVirtualFen = _laboPgnFens[_laboPgnIdx];
  laboShowVirtualFen();
  _laboRenderPgnHistory();
  _laboRenderPgnLeft();
}

function laboPgnPrev() {
  if (_laboPgnIdx > 0) {
    _laboPgnIdx--;
    _laboVirtualFen = _laboPgnFens[_laboPgnIdx];
    laboShowVirtualFen();
    _laboRenderPgnHistory();
    _laboRenderPgnLeft();
  }
}
function laboPgnNext() {
  if (_laboPgnIdx < _laboPgnFens.length - 1) {
    _laboPgnIdx++;
    _laboVirtualFen = _laboPgnFens[_laboPgnIdx];
    laboShowVirtualFen();
    _laboRenderPgnHistory();
    _laboRenderPgnLeft();
  }
}

function laboShowVirtualFen() {
  // Afficher la position virtuelle sur l'échiquier labo
  laboRenderBoard(_laboVirtualFen, null, null);
  const sanEl = document.getElementById("labo-pgn-san");
  if (sanEl) {
    sanEl.textContent = _laboPgnIdx > 0 ? (_laboPgnMoves[_laboPgnIdx - 1] || "") : "Position initiale";
  }
}

function laboCopyToBoard() {
  if (!_laboVirtualFen) return;
  _laboCopyMode = true;
  sendAction({ type: "labo_copy_to_board", fen: _laboVirtualFen });
  laboJournalAdd("config", "📋 Source virtuelle → Plateau activé");
}

function laboSyncPhysique() {
  sendAction({ type: "source_physique", turn: _laboTurn });
  laboJournalAdd("config", "🔄 Source physique → Virtuel");
}

// Mise à jour de l'échiquier labo depuis le plateau physique
socket.on("board_fen_update", (data) => {
  const screen = document.getElementById("screen-labo");
  if (!screen || screen.style.display === "none") return;
  // Ne mettre à jour que si pas en mode position virtuelle active
  if (!_laboVirtualFen) {
    laboRenderBoard(data.fen, null, null);
  }
});

// ── Labo ─────────────────────────────────────────────────────────────────────

let _laboAutoOn  = false;

// ── Journal d'événements ─────────────────────────────────────────────────────

const _JOURNAL_MAX = 50;
const _COLORS = {
  coups:   "#e0e0e0",
  alertes: "#ff9800",
  analyse: "#4caf50",
  config:  "#aac4e0",
};
let _journalFiltres = new Set(["coups", "alertes", "analyse", "config"]);

function laboJournalAdd(cat, msg) {
  const journal = document.getElementById("labo-journal");
  if (!journal) return;
  const now = new Date();
  const hms = now.toTimeString().slice(0, 8);
  const entry = document.createElement("div");
  entry.className = "jlog-entry";
  entry.dataset.cat = cat;
  entry.style.display = _journalFiltres.has(cat) ? "flex" : "none";
  entry.innerHTML = `<span class="jlog-time">${hms}</span><span class="jlog-msg" style="color:${_COLORS[cat] || "#aaa"};">${msg}</span>`;
  journal.insertBefore(entry, journal.firstChild);
  // Limiter à _JOURNAL_MAX entrées
  while (journal.children.length > _JOURNAL_MAX) {
    journal.removeChild(journal.lastChild);
  }
}

function laboJournalVider() {
  const j = document.getElementById("labo-journal");
  if (j) j.innerHTML = "";
}

function laboSwitchTab(tab) {
  const tabJ = document.getElementById("labo-tab-journal");
  const tabP = document.getElementById("labo-tab-pgn");
  const panJ = document.getElementById("labo-tab-panel-journal");
  const panP = document.getElementById("labo-tab-panel-pgn");
  if (tab === "journal") {
    if (tabJ) { tabJ.style.borderBottomColor = "#e94560"; tabJ.style.color = "#e0e0e0"; }
    if (tabP) { tabP.style.borderBottomColor = "transparent"; tabP.style.color = "#556"; }
    if (panJ) panJ.style.display = "flex";
    if (panP) panP.style.display = "none";
  } else {
    if (tabP) { tabP.style.borderBottomColor = "#e94560"; tabP.style.color = "#e0e0e0"; }
    if (tabJ) { tabJ.style.borderBottomColor = "transparent"; tabJ.style.color = "#556"; }
    if (panJ) panJ.style.display = "none";
    if (panP) panP.style.display = "flex";
  }
}

function _laboRenderPgnLeft() {
  const moves = document.getElementById("labo-pgn-moves");
  const info  = document.getElementById("labo-pgn-info-left");
  if (!moves || !_laboPgnMoves.length) return;
  if (info) info.textContent = document.getElementById("labo-pgn-info")?.textContent || "";
  let html = '<table style="width:100%;border-collapse:collapse;">';
  const total = Math.ceil(_laboPgnMoves.length / 2);
  for (let i = 0; i < total; i++) {
    const wIdx = i * 2;
    const bIdx = i * 2 + 1;
    const active = _laboPgnIdx - 1;
    const cwW = active === wIdx ? "color:#e94560;font-weight:bold;" : "color:#ccc;";
    const cwB = active === bIdx ? "color:#e94560;font-weight:bold;" : "color:#888;";
    html += `<tr>`;
    html += `<td style="color:#444;text-align:right;padding-right:4px;font-size:0.68rem;width:20px;">${i+1}.</td>`;
    html += _laboPgnMoves[wIdx]
      ? `<td style="padding:1px 3px;cursor:pointer;${cwW}" onclick="laboPgnGoTo(${wIdx+1})">${_laboPgnMoves[wIdx]}</td>`
      : `<td></td>`;
    html += _laboPgnMoves[bIdx]
      ? `<td style="padding:1px 3px;cursor:pointer;${cwB}" onclick="laboPgnGoTo(${bIdx+1})">${_laboPgnMoves[bIdx]}</td>`
      : `<td></td>`;
    html += `</tr>`;
  }
  html += '</table>';
  moves.innerHTML = html;
  // Scroller vers le coup actif
  setTimeout(() => {
    const active = moves.querySelector('[style*="color:#e94560"]');
    if (active) active.scrollIntoView({ block: "center" });
  }, 50);
}

function laboJournalToggleFilt(cat) {
  const btn = document.getElementById(`jfilt-${cat}`);
  if (_journalFiltres.has(cat)) {
    _journalFiltres.delete(cat);
    if (btn) btn.classList.remove("active");
  } else {
    _journalFiltres.add(cat);
    if (btn) btn.classList.add("active");
  }
  // Mettre à jour la visibilité
  const journal = document.getElementById("labo-journal");
  if (!journal) return;
  for (const entry of journal.children) {
    entry.style.display = _journalFiltres.has(entry.dataset.cat) ? "flex" : "none";
  }
}
let _laboCamp    = "white"; // camp humain courant

function laboToggleSection(id) {
  const sec   = document.getElementById(id);
  const arrow = document.getElementById(id + "-arrow");
  if (!sec) return;
  const open = sec.style.display !== "none";
  sec.style.display   = open ? "none" : "flex";
  if (arrow) arrow.textContent = open ? "▼" : "▲";
}

function laboUpdateEvalBar(cp, mate) {
  const barBlack = document.getElementById("labo-eval-black");
  const barWhite = document.getElementById("labo-eval-white");
  const scoreEl  = document.getElementById("labo-eval-score");
  if (!barBlack || !barWhite) return;

  let pctWhite = 50; // % pour les blancs
  let scoreText = "0.0";

  if (mate !== null && mate !== undefined) {
    pctWhite = mate > 0 ? 100 : 0;
    scoreText = mate > 0 ? `M${mate}` : `M${Math.abs(mate)}`;
  } else if (cp !== null && cp !== undefined) {
    // Convertir cp en pourcentage (sigmoid)
    const clamped = Math.max(-1000, Math.min(1000, cp));
    pctWhite = 50 + 50 * (2 / (1 + Math.exp(-0.004 * clamped)) - 1);
    const abs = Math.abs(cp / 100).toFixed(2);
    scoreText = cp >= 0 ? `+${abs}` : `-${abs}`;
  }

  const pctBlack = 100 - pctWhite;
  barBlack.style.height = `${pctBlack}%`;
  barWhite.style.height = `${pctWhite}%`;
  if (scoreEl) {
    scoreEl.textContent = scoreText;
    scoreEl.style.color = cp >= 0 ? "#e0e0e0" : "#aaa";
  }
}

let _laboTurn = "white"; // tour actuel pour sync_from_physical
let _laboTurnForced = false; // true si l'utilisateur a forcé manuellement

function laboSetCamp(camp) {
  if (_laboCamp === camp) return;
  _laboCamp = camp;
  _laboUpdateCampBtn();
  sendAction({ type: "labo_set_config", human_color: camp });
  laboJournalAdd("config", `Je joue ${camp === "white" ? "♔ Blancs" : "♚ Noirs"}`);
}

function laboSetTurn(turn) {
  if (_laboTurn === turn && _laboTurnForced) return;
  _laboTurn = turn;
  _laboTurnForced = true;
  _laboUpdateTurnBtn();
  sendAction({ type: "labo_set_turn", turn: turn });
  laboJournalAdd("config", `Tour : ${turn === "white" ? "♔ Blancs" : "♚ Noirs"}`);
}

function _laboUpdateTurnBtn() {
  const btnW = document.getElementById("labo-turn-white");
  const btnB = document.getElementById("labo-turn-black");
  if (!btnW || !btnB) return;
  if (_laboTurn === "white") {
    btnW.style.background = "#e94560"; btnW.style.color = "#fff";
    btnB.style.background = "#16213e"; btnB.style.color = "#555";
  } else {
    btnW.style.background = "#16213e"; btnW.style.color = "#555";
    btnB.style.background = "#4caf50"; btnB.style.color = "#fff";
  }
}

function _laboUpdateCampBtn() {
  const btnW = document.getElementById("labo-camp-white");
  const btnB = document.getElementById("labo-camp-black");
  if (!btnW || !btnB) return;
  if (_laboCamp === "white") {
    btnW.style.background = "#e94560"; btnW.style.color = "#fff";
    btnB.style.background = "#16213e"; btnB.style.color = "#555";
  } else {
    btnW.style.background = "#16213e"; btnW.style.color = "#555";
    btnB.style.background = "#4caf50"; btnB.style.color = "#fff";
  }
}

function laboBuildBoard() {
  const board = document.getElementById("labo-board");
  if (!board || board.children.length) return;
  const rankCoord = document.getElementById("labo-coord-rank");
  if (rankCoord) {
    rankCoord.innerHTML = "";
    for (let r = 7; r >= 0; r--) {
      const s = document.createElement("span"); s.textContent = r + 1; rankCoord.appendChild(s);
    }
  }
  const fileCoord = document.getElementById("labo-coord-file");
  if (fileCoord) {
    fileCoord.innerHTML = "";
    "abcdefgh".split("").forEach(f => {
      const s = document.createElement("span"); s.textContent = f; fileCoord.appendChild(s);
    });
  }
  board.innerHTML = "";
  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const sq = document.createElement("div");
      const isLight = (rank + file) % 2 === 1;
      sq.className = `square ${isLight ? "light" : "dark"}`;
      sq.id = `labo-sq-${file}-${rank}`;
      board.appendChild(sq);
    }
  }
}

function laboRenderBoard(fen, from, to) {
  laboBuildBoard();
  const grid = fenToBoard(fen);
  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const id = `${file}-${rank}`;
      const sq = document.getElementById(`labo-sq-${id}`);
      if (!sq) continue;
      const piece = grid[id];
      sq.innerHTML = piece ? (PIECES[piece] || piece) : "";
      const isLight = (rank + file) % 2 === 1;
      sq.className = `square ${isLight ? "light" : "dark"}`;
      if (from && id === from) sq.classList.add("last-move-from");
      if (to   && id === to)   sq.classList.add("last-move-to");
    }
  }
}

function laboToggleAuto() {
  _laboAutoOn = !_laboAutoOn;
  sendAction({type: "engine_auto", value: _laboAutoOn});
  laboJournalAdd("config", `Auto ${_laboAutoOn ? "ON ▶" : "OFF ◼"}`);
}

function _laboUpdateAutoBtn(auto) {
  _laboAutoOn = auto;
  const btn = document.getElementById("labo-btn-auto");
  if (!btn) return;
  if (auto) {
    btn.textContent = "⏸ Auto ON";
    btn.style.background   = "#e94560";
    btn.style.color        = "#fff";
    btn.style.borderColor  = "#e94560";
  } else {
    btn.textContent = "⏵ Auto OFF";
    btn.style.background   = "#0f3460";
    btn.style.color        = "#e0e0e0";
    btn.style.borderColor  = "#333";
  }
}

socket.on("labo_init", (data) => {
  laboBuildBoard();
  _laboCamp = data.human_color || "white";
  _laboUpdateCampBtn();
  const sub   = document.getElementById("labo-game-subtitle");
  const engEl = document.getElementById("labo-engine-label");
  if (sub)   sub.textContent = `Laboratoire — ${data.engine_label}`;
  if (engEl) engEl.textContent = data.engine_label || "";
  const engInfoEl = document.getElementById("labo-engine-info");
  if (engInfoEl) engInfoEl.textContent = data.engine_label || "";
  const topEl = document.getElementById("labo-player-top");
  const botEl = document.getElementById("labo-player-bottom");
  if (topEl) topEl.textContent = "Noirs";
  if (botEl) botEl.textContent = "Blancs ★";
  _laboUpdateAutoBtn(false);
  const fb = document.getElementById("labo-feedback");
  if (fb) fb.style.display = "none";
  const evalEl = document.getElementById("labo-eval");
  if (evalEl) evalEl.textContent = "";
  // Journal
  laboJournalAdd("config", `⚙ ${data.engine_label} — Je joue ${data.human_color === "white" ? "Blancs" : "Noirs"}`);
});

socket.on("labo_position", (data) => {
  laboRenderBoard(data.fen, data.from, data.to);
  const turnEl = document.getElementById("labo-turn-info");
  const turnIsWhite = data.turn === "white";
  // Effacer le message d'échec si plus en échec
  const lastEl0 = document.getElementById("labo-last-move");
  if (lastEl0 && !data.in_check && lastEl0.textContent.startsWith("⚠ Échec")) {
    lastEl0.textContent = "";
  }
  if (turnEl) {
    if (data.in_check) {
      turnEl.textContent = "⚠ Échec !";
      turnEl.style.color = "#ff9800";
    } else if (data.engine_turn && data.auto) {
      // Moteur va jouer — message placez le coup sera envoyé par labo_engine_played
      turnEl.textContent = "Tour du moteur...";
      turnEl.style.color = "#aaa";
    } else if (data.engine_turn && !data.auto) {
      turnEl.textContent = "Tour du moteur (Auto OFF)";
      turnEl.style.color = "#556";
    } else {
      turnEl.textContent = "À votre tour";
      turnEl.style.color = "#e0e0e0";
    }
  }
  // ★ sur le camp dont c'est le tour
  const topEl2 = document.getElementById("labo-player-top");
  const botEl2 = document.getElementById("labo-player-bottom");
  if (topEl2) topEl2.textContent = "Noirs" + (turnIsWhite ? "" : " ★");
  if (botEl2) botEl2.textContent = "Blancs" + (turnIsWhite ? " ★" : "");
  // Mettre à jour le toggle Tour pour refléter le tour courant
  // (seulement si pas forcé manuellement)
  if (!_laboTurnForced) {
    _laboTurn = data.turn;
    _laboUpdateTurnBtn();
  }
  const btnUndo = document.getElementById("labo-btn-undo");
  if (btnUndo) {
    btnUndo.disabled = !data.can_undo;
    btnUndo.style.opacity = data.can_undo ? "1" : "0.4";
  }
  _laboUpdateAutoBtn(data.auto);
  // Source physique toujours disponible
  const btnSrcPhys = document.getElementById("labo-btn-source-physique");
  if (btnSrcPhys) btnSrcPhys.style.display = "block";
});

socket.on("labo_best_move", (data) => {
  laboUpdateEvalBar(data.cp, data.mate);
  const lastEl = document.getElementById("labo-last-move");
  let txt = `💡 ${data.san}`;
  if (lastEl) {
    if (data.cp !== null && data.cp !== undefined) {
      const sign = data.cp > 0 ? "+" : "";
      txt += ` (${sign}${(data.cp/100).toFixed(2)})`;
    } else if (data.mate) {
      txt += ` (M${Math.abs(data.mate)})`;
    }
    lastEl.textContent = txt;
    lastEl.style.color = "#4caf50";
  }
  laboJournalAdd("analyse", txt);
  // Flèches sur échiquier
  if (data.uci && data.uci.length >= 4) {
    const [bFrom, bTo] = uciToCoords(data.uci);
    const sqF = document.getElementById(`labo-sq-${bFrom}`);
    const sqT = document.getElementById(`labo-sq-${bTo}`);
    if (sqF) sqF.classList.add("highlight-best-from");
    if (sqT) sqT.classList.add("highlight-best-to");
    setTimeout(() => {
      if (sqF) sqF.classList.remove("highlight-best-from");
      if (sqT) sqT.classList.remove("highlight-best-to");
    }, 5000);
  }
});

socket.on("labo_engine_played", (data) => {
  const lastEl = document.getElementById("labo-last-move");
  if (lastEl) {
    lastEl.textContent = `♟ ${data.engine} : ${data.san}`;
    lastEl.style.color = "#aac4e0";
  }
  const turnEl = document.getElementById("labo-turn-info");
  if (turnEl) {
    turnEl.textContent = `Placez le coup de ${data.engine}`;
    turnEl.style.color = "#ff9800";
  }
  laboJournalAdd("coups", `♟ ${data.engine} : ${data.san}`);
});

socket.on("labo_free_position", (data) => {
  laboRenderBoard(data.fen, null, null);
});

// Coups joués (humain) — on les capte via labo_position quand from+to présents
// On utilise plutôt le handler move pour les enregistrer dans le journal
const _laboMoveHandler_orig = socket.listeners ? null : null;
socket.on("move", (data) => {
  // Enregistrer dans le journal si on est dans l'écran labo
  const laboScreen = document.getElementById("screen-labo");
  if (!laboScreen || laboScreen.style.display === "none") return;
  if (data.player !== "Joueur") return; // moteur géré par labo_engine_played
  const colorSym = data.color === "white" ? "♔" : "♚";
  laboJournalAdd("coups", `${colorSym} ${data.san}`);
});

socket.on("labo_placement_cancelled", () => {
  // Auto désactivé pendant l'attente de placement — effacer le libellé moteur
  const lastEl = document.getElementById("labo-last-move");
  if (lastEl) { lastEl.textContent = ""; }
  const turnEl = document.getElementById("labo-turn-info");
  if (turnEl) { turnEl.textContent = "Auto désactivé"; turnEl.style.color = "#556"; }
});

socket.on("labo_auto", (data) => {
  _laboUpdateAutoBtn(data.auto);
});

socket.on("labo_feedback", (data) => {
  const msg = `${data.label} — ${data.san} (${data.delta_cp}cp)`;
  laboJournalAdd("alertes", msg);
  // Aussi dans last-move brièvement
  const lastEl = document.getElementById("labo-last-move");
  if (lastEl) {
    const colors = { imprecision: "#e65100", erreur: "#b71c1c", blunder: "#e94560" };
    lastEl.textContent = msg;
    lastEl.style.color = colors[data.qualite] || "#e94560";
    setTimeout(() => { if (lastEl.textContent === msg) lastEl.textContent = ""; }, 5000);
  }
});

socket.on("labo_analyse", (data) => {
  laboUpdateEvalBar(data.cp, data.mate);
  const lastEl = document.getElementById("labo-last-move");
  if (data.best_san && lastEl) {
    lastEl.textContent = `🔍 ${data.best_san}`;
    lastEl.style.color = "#4caf50";
  }
  if (data.best_move && data.best_move.length >= 4) {
    const [bFrom, bTo] = uciToCoords(data.best_move);
    const sqFrom = document.getElementById(`labo-sq-${bFrom}`);
    const sqTo   = document.getElementById(`labo-sq-${bTo}`);
    if (sqFrom) sqFrom.classList.add("highlight-best-from");
    if (sqTo)   sqTo.classList.add("highlight-best-to");
    setTimeout(() => {
      if (sqFrom) sqFrom.classList.remove("highlight-best-from");
      if (sqTo)   sqTo.classList.remove("highlight-best-to");
    }, 5000);
  }
});

socket.on("labo_info", (data) => {
  const lastEl = document.getElementById("labo-last-move");
  if (lastEl) {
    lastEl.textContent = data.message;
    lastEl.style.color = data.type === "sync" ? "#4caf50" : "#e94560";
  }
  if (data.type !== "sync") {
    const turnEl = document.getElementById("labo-turn-info");
    if (turnEl) { turnEl.textContent = data.message; turnEl.style.color = "#e94560"; }
  }
  // Journal
  const cat = ["sync","config"].includes(data.type) ? "config" : "alertes";
  laboJournalAdd(cat, data.message);
  afficherToast(data.message, data.type === "sync" ? "success" : "info");
});

socket.on("labo_copy_start", (data) => {
  if (data.target_fen) {
    laboRenderBoard(data.target_fen, null, null);
    const turnEl = document.getElementById("labo-turn-info");
    if (turnEl) {
      turnEl.textContent = "Reproduisez cette position sur le plateau";
      turnEl.style.color = "#ff9800";
    }
    // Effacer le message précédent (ex: "Synchronisé")
    const lastEl = document.getElementById("labo-last-move");
    if (lastEl) { lastEl.textContent = ""; }
  }
});



// Aussi gérer les moves du labo via socket.on("move") existant
// → déjà géré car labo_position met à jour l'échiquier

// ── Audio ─────────────────────────────────────────────────────────────────────

function playBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 440;
    osc.type = 'sine';
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.15);
  } catch (e) {}
}

// ── Exercices ─────────────────────────────────────────────────────────────────

let _exColor       = "white";
let _exVariete     = 3;
let _exOuvertureId = "";
let _exTab         = "white";   // onglet actif
let _exOuvertures  = [];        // cache pour re-render au changement d'onglet

// Couleurs par famille
const _EX_FAMILY_COLORS = { e4: "#1565c0", d4: "#6a1b9a", other: "#2e7d32" };
const _EX_FAMILY_LABELS = { e4: "1.e4", d4: "1.d4", other: "Autres" };

function _exFamily(o) {
  const first = (o.init || [])[0] || "";
  if (first === "e2e4") return "e4";
  if (first === "d2d4") return "d4";
  return "other";
}

function exSelectTab(tab) {
  _exTab = tab;
  // Styles onglets
  const wBtn = document.getElementById("ex-tab-white");
  const bBtn = document.getElementById("ex-tab-black");
  if (wBtn) { wBtn.style.background = tab === "white" ? "#e8c840" : "#16213e"; wBtn.style.color = tab === "white" ? "#1a1a2e" : "#778"; }
  if (bBtn) { bBtn.style.background = tab === "black" ? "#444"   : "#16213e"; bBtn.style.color = tab === "black" ? "#e0e0e0" : "#778"; }
  // Mettre à jour _exColor pour que les cartes lancent avec le bon camp
  _exColor = tab;
  exRenderOuvertures(_exOuvertures);
}

function exUpdateVariete() {
  _exVariete = parseInt(document.getElementById("ex-variete")?.value || 3);
  const lbl = document.getElementById("ex-variete-label");
  if (lbl) lbl.textContent = _exVariete;
}

// ── Mini échiquier SVG pour les cartes d'ouverture ───────────────────────────

const _EX_MINI_PIECES = {
  K:"♔",Q:"♕",R:"♖",B:"♗",N:"♘",P:"♙",
  k:"♚",q:"♛",r:"♜",b:"♝",n:"♞",p:"♟",
};

function _exMiniBoardSvg(initMoves) {
  // Rejouer les coups sur un board virtuel
  const grid = {};
  // Position initiale
  const startRows = ["rnbqkbnr","pppppppp","","","","","PPPPPPPP","RNBQKBNR"];
  for (let rank = 0; rank < 8; rank++) {
    let file = 0;
    for (const ch of startRows[7 - rank]) {
      if (ch >= "1" && ch <= "8") { file += parseInt(ch); }
      else { grid[`${file},${rank}`] = ch; file++; }
    }
  }
  const files = "abcdefgh";
  for (const uci of (initMoves || [])) {
    if (uci.length < 4) continue;
    const fc = files.indexOf(uci[0]), fr = parseInt(uci[1]) - 1;
    const tc = files.indexOf(uci[2]), tr = parseInt(uci[3]) - 1;
    const piece = grid[`${fc},${fr}`];
    if (piece) { delete grid[`${fc},${fr}`]; grid[`${tc},${tr}`] = piece; }
  }
  // Derniers coups surlignés
  const lastUci = initMoves && initMoves.length ? initMoves[initMoves.length - 1] : null;
  let hlFrom = null, hlTo = null;
  if (lastUci && lastUci.length >= 4) {
    hlFrom = `${files.indexOf(lastUci[0])},${parseInt(lastUci[1])-1}`;
    hlTo   = `${files.indexOf(lastUci[2])},${parseInt(lastUci[3])-1}`;
  }
  const SZ = 120, sq = SZ / 8;
  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${SZ}" height="${SZ}" style="display:block;border-radius:3px;overflow:hidden;">`;
  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const x = file * sq, y = (7 - rank) * sq;
      const key = `${file},${rank}`;
      const light = (rank + file) % 2 === 1;
      let fill = light ? "#f0d9b5" : "#b58863";
      if (key === hlFrom || key === hlTo) fill = light ? "#cdd16f" : "#aaa23a";
      svg += `<rect x="${x}" y="${y}" width="${sq}" height="${sq}" fill="${fill}"/>`;
      const piece = grid[key];
      if (piece) {
        const sym = _EX_MINI_PIECES[piece] || "";
        const color = piece === piece.toUpperCase() ? "#fff" : "#111";
        const stroke = piece === piece.toUpperCase() ? "#333" : "#ddd";
        svg += `<text x="${x + sq/2}" y="${y + sq*0.78}" text-anchor="middle" font-size="${sq*0.82}" fill="${color}" stroke="${stroke}" stroke-width="0.4" paint-order="stroke">${sym}</text>`;
      }
    }
  }
  svg += `</svg>`;
  return svg;
}

// ── Hiérarchie ECO : racine vs variante ──────────────────────────────────────

function _exBuildHierarchy(allOuvertures, tabColor) {
  // Hiérarchie basée sur parent_eco (champ écrit par eco_import depuis eco_hierarchy.json)
  // Fallback : plage ECO pour les ouvertures sans parent_eco

  const filtered = allOuvertures.filter(o => (o.camp_suggere||"white") === tabColor);

  // Index par ECO pour résoudre les parent_eco
  const byEco = {};
  for (const o of allOuvertures) {
    byEco[o.eco] = byEco[o.eco] || o;
  }

  const variantsByRoot = {};
  const childIds = new Set();

  for (const v of filtered) {
    if ((v.eco||"").includes("-")) continue;  // plages ECO = toujours racines

    let parent = null;

    // Règle 1 : parent_eco explicite (depuis eco_hierarchy.json via eco_import)
    if (v.parent_eco) {
      // Chercher le parent dans allOuvertures par code ECO exact
      parent = allOuvertures.find(r => r.eco === v.parent_eco || r.eco.startsWith(v.parent_eco));
    }

    // Règle 2 : plage ECO (fallback pour ouvertures sans parent_eco)
    if (!parent) {
      parent = allOuvertures.find(r => {
        if (!r.eco || !r.eco.includes("-")) return false;
        const [lo, hi] = r.eco.split("-");
        return lo <= v.eco && v.eco <= hi;
      });
    }

    if (parent) {
      if (!variantsByRoot[parent.id]) variantsByRoot[parent.id] = [];
      variantsByRoot[parent.id].push(v);
      childIds.add(v.id);
    }
  }

  // Racines = ouvertures de l'onglet sans parent
  // + parents cross-camp (ex: Ruy Lopez white avec variantes black)
  const crossRoots = allOuvertures.filter(r =>
    (r.camp_suggere||"white") !== tabColor &&
    variantsByRoot[r.id]?.length > 0
  );
  const allRoots = [
    ...filtered.filter(o => !childIds.has(o.id)),
    ...crossRoots,
  ];

  return { allRoots, variantsByRoot };
}

function _exBuildCard(o, color, nbVariants, onClick, isVariant) {
  const bg     = isVariant ? "rgba(255,215,0,0.07)" : "#16213e";
  const border = isVariant ? `${color}88` : `${color}44`;
  const card = document.createElement("div");
  card.style.cssText = `background:${bg}; border:2px solid ${border}; border-radius:8px; padding:12px 14px; width:210px; cursor:pointer; transition:border-color 0.15s; box-sizing:border-box; display:flex; flex-direction:column; position:relative;`;
  card.onmouseover = () => card.style.borderColor = color;
  card.onmouseout  = () => card.style.borderColor = border;
  const miniBoard = _exMiniBoardSvg(o.init || []);
  const badge = nbVariants > 0
    ? `<div style="margin-top:8px; font-size:0.72rem; color:${color}; text-align:center; border-top:1px solid ${color}33; padding-top:6px;">` +
      `${nbVariants} variante${nbVariants > 1 ? "s" : ""} <span id="ex-chevron-${o.id}">▼</span></div>`
    : "";
  card.innerHTML = `
    <div style="font-size:0.7rem; color:${color}${isVariant ? "cc" : "88"}; margin-bottom:3px;">${o.eco}</div>
    <div style="font-size:0.85rem; font-weight:bold; color:#e0e0e0; margin-bottom:8px; line-height:1.3;">${o.nom}</div>
    <div style="display:flex; justify-content:center;">${miniBoard}</div>
    ${badge}
  `;
  card.onclick = onClick;
  // Bouton ▶ Jouer sur les cartes racines avec variantes
  if (nbVariants > 0) {
    const btn = document.createElement("button");
    btn.textContent = "▶";
    btn.title = "Jouer cette ouverture";
    btn.style.cssText = `position:absolute; top:6px; right:8px; background:none; border:none; color:${color}; font-size:0.9rem; cursor:pointer; opacity:0.5; padding:2px 4px; line-height:1; transition:opacity 0.15s;`;
    btn.onmouseover = (e) => { e.stopPropagation(); btn.style.opacity = "1"; btn.title = "Jouer cette ouverture"; };
    btn.onmouseout  = (e) => { e.stopPropagation(); btn.style.opacity = "0.5"; };
    btn.onclick = (e) => { e.stopPropagation(); exLancer(o.id); };
    card.appendChild(btn);
  }
  return card;
}

function exRenderOuvertures(ouvertures) {
  _exOuvertures = ouvertures;
  const list = document.getElementById("ex-ouvertures-list");
  if (!list) return;
  list.innerHTML = "";

  // Filtrer par camp suggéré = onglet actif
  const filtered = ouvertures.filter(o => (o.camp_suggere || "white") === _exTab);

  // Construire hiérarchie
  const { allRoots, variantsByRoot } = _exBuildHierarchy(ouvertures, _exTab);
  const groups = { e4: [], d4: [], other: [] };
  for (const o of allRoots) groups[_exFamily(o)].push(o);

  for (const [fam, items] of Object.entries(groups)) {
    if (!items.length) continue;
    const color  = _EX_FAMILY_COLORS[fam];
    const label  = _EX_FAMILY_LABELS[fam];
    const domKey = `ex-fam-open-${_exTab}-${fam}`;

    const section = document.createElement("div");
    section.style.cssText = "margin-bottom:16px;";

    // Header famille (e4 / d4 / Autres)
    const header = document.createElement("div");
    const isOpen = sessionStorage.getItem(domKey) !== "closed";
    const totalItems = items.reduce((n, o) => n + 1 + (variantsByRoot[o.id] || []).length, 0);
    header.style.cssText = `display:flex; align-items:center; gap:10px; padding:8px 14px; background:${color}22; border-left:4px solid ${color}; border-radius:4px; cursor:pointer; user-select:none; margin-bottom:${isOpen ? "10px" : "0"};`;
    header.innerHTML = `<span style="color:${color}; font-weight:bold; font-size:0.95rem;">${label}</span><span style="color:#aaa; font-size:0.82rem;">${totalItems} ouverture${totalItems > 1 ? "s" : ""}</span><span style="margin-left:auto; color:${color}; font-size:1rem;">${isOpen ? "▲" : "▼"}</span>`;

    const famContent = document.createElement("div");
    famContent.style.cssText = `display:${isOpen ? "block" : "none"};`;

    header.onclick = () => {
      const open = famContent.style.display === "none";
      famContent.style.display = open ? "block" : "none";
      header.style.marginBottom = open ? "10px" : "0";
      header.querySelector("span:last-child").textContent = open ? "▲" : "▼";
      sessionStorage.setItem(domKey, open ? "open" : "closed");
    };

    // Conteneur principal : grille + panneaux en pleine largeur intercalés
    const famBody = document.createElement("div");
    famContent.appendChild(famBody);

    // Une expansion active à la fois par famille
    let activePanel = null;
    let activeChev  = null;
    let activeKey   = null;

    const famGrid = document.createElement("div");
    famGrid.style.cssText = "display:flex; flex-wrap:wrap; gap:12px; padding:0 4px 4px;";
    famBody.appendChild(famGrid);

    // Panneau pleine largeur pour les variantes
    const varExpand = document.createElement("div");
    varExpand.style.cssText = `display:none; flex-wrap:wrap; gap:10px; padding:12px 16px; margin-top:8px; background:${color}0d; border-left:3px solid ${color}; border-radius:0 6px 6px 0;`;
    famBody.appendChild(varExpand);

    // Titre du panneau
    const varTitle = document.createElement("div");
    varTitle.style.cssText = `width:100%; font-size:0.8rem; color:${color}; font-weight:bold; margin-bottom:8px; padding-bottom:6px; border-bottom:1px solid ${color}33;`;
    varExpand.appendChild(varTitle);

    function toggleVariants(o, childVariants, card) {
      const rootKey = `ex-root-open-${_exTab}-${o.id}`;
      const isAlreadyOpen = activeKey === o.id && varExpand.style.display !== "none";

      // Fermer l'expansion courante
      varExpand.style.display = "none";
      if (activeChev) activeChev.textContent = "▼";
      activeKey = null; activeChev = null;

      if (isAlreadyOpen) {
        sessionStorage.removeItem(rootKey);
        return;
      }

      // Ouvrir pour cette ouverture
      const chev = card.querySelector(`#ex-chevron-${o.id}`);
      if (chev) chev.textContent = "▲";
      activeChev = chev;
      activeKey  = o.id;
      sessionStorage.setItem(rootKey, "open");

      // Remplir le panneau
      varTitle.textContent = o.nom + " — variantes";
      // Supprimer anciennes cartes (garder le titre)
      while (varExpand.children.length > 1) varExpand.removeChild(varExpand.lastChild);
      for (const v of childVariants) {
        varExpand.appendChild(_exBuildCard(v, color, 0, () => exLancer(v.id), true));
      }
      varExpand.style.display = "flex";
      varExpand.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    // Pour chaque ouverture racine dans cette famille
    for (const o of items) {
      const childVariants = variantsByRoot[o.id] || [];
      const hasVariants   = childVariants.length > 0;

      const card = _exBuildCard(o, color, childVariants.length, () => {
        if (hasVariants) {
          toggleVariants(o, childVariants, card);
        } else {
          exLancer(o.id);
        }
      }, false);

      if (hasVariants) {
        card.ondblclick = (e) => { e.stopPropagation(); exLancer(o.id); };
        card.title = "Clic : voir variantes — Double-clic : jouer cette ligne";
      }

      famGrid.appendChild(card);

      // Restaurer état ouvert depuis sessionStorage
      const rootKey = `ex-root-open-${_exTab}-${o.id}`;
      if (sessionStorage.getItem(rootKey) === "open" && hasVariants) {
        setTimeout(() => toggleVariants(o, childVariants, card), 0);
      }
    }

    section.appendChild(header);
    section.appendChild(famContent);
    list.appendChild(section);
  }

  if (!filtered.length) {
    list.innerHTML = `<div style="color:#556; text-align:center; padding:20px;">Aucune ouverture dans cet onglet.</div>`;
  }
}

function exLancer(ouvertureId) {
  _exOuvertureId = ouvertureId;
  // Afficher spinner en attendant exercice_init
  const spinner = document.getElementById("ex-spinner");
  const wrapper = document.getElementById("ex-board-wrapper");
  if (spinner) spinner.style.display = "flex";
  if (wrapper) wrapper.style.display = "none";
  sendAction({
    type:         "start_exercice",
    ouverture_id: ouvertureId,
    human_color:  _exColor,
    variete:      _exVariete,
  });
}

// Construire l'échiquier de l'exercice
function exBuildBoard() {
  const board = document.getElementById("ex-board");
  if (!board || board.children.length) return;
  const rankCoord = document.getElementById("ex-coord-rank");
  if (rankCoord) {
    rankCoord.innerHTML = "";
    for (let r = 7; r >= 0; r--) {
      const s = document.createElement("span"); s.textContent = r + 1; rankCoord.appendChild(s);
    }
  }
  const fileCoord = document.getElementById("ex-coord-file");
  if (fileCoord) {
    fileCoord.innerHTML = "";
    "abcdefgh".split("").forEach(f => {
      const s = document.createElement("span"); s.textContent = f; fileCoord.appendChild(s);
    });
  }
  board.innerHTML = "";
  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const sq = document.createElement("div");
      sq.className = `square ${(rank + file) % 2 === 1 ? "light" : "dark"}`;
      sq.id = `ex-sq-${file}-${rank}`;
      board.appendChild(sq);
    }
  }
}

function exRenderBoard(fen, from, to) {
  exBuildBoard();
  const grid = fenToBoard(fen);
  const files = "abcdefgh";
  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const id = `${file}-${rank}`;
      const sq = document.getElementById(`ex-sq-${id}`);
      if (!sq) continue;
      const piece = grid[id];
      sq.innerHTML = piece ? (PIECES[piece] || piece) : "";
      sq.className = `square ${(rank + file) % 2 === 1 ? "light" : "dark"}`;
      if (from && id === from) sq.classList.add("last-move-from");
      if (to   && id === to)   sq.classList.add("last-move-to");
    }
  }
}

// ── Traduction SAN → français ─────────────────────────────────────────────────

const _SAN_PIECES = { K: "Roi", Q: "Dame", R: "Tour", B: "Fou", N: "Cavalier" };

function sanToFr(san) {
  if (!san) return san;
  if (san.startsWith("O-O-O") || san.startsWith("0-0-0")) return "Grand roque" + _sanSuffix(san.slice(5));
  if (san.startsWith("O-O")   || san.startsWith("0-0"))   return "Petit roque"  + _sanSuffix(san.slice(3));
  let base = san, suffix = "";
  if (base.endsWith("#"))      { suffix = " mat";   base = base.slice(0, -1); }
  else if (base.endsWith("+")) { suffix = " échec";  base = base.slice(0, -1); }
  let promo = "";
  const promoMatch = base.match(/=([QRBN])$/);
  if (promoMatch) { promo = "=" + _SAN_PIECES[promoMatch[1]]; base = base.slice(0, -2); }
  let piece = "";
  if (base[0] && _SAN_PIECES[base[0]]) { piece = _SAN_PIECES[base[0]]; base = base.slice(1); }
  else piece = "pion";
  const capture = base.includes("x");
  base = base.replace("x", "");
  const targetSq = base.slice(-2);
  const disambig = base.slice(0, -2);
  let result = piece;
  if (disambig) result += ` (${disambig})`;
  result += capture ? " prend en " + targetSq : " en " + targetSq;
  return result + promo + suffix;
}

function _sanSuffix(s) {
  if (s.startsWith("#")) return " mat";
  if (s.startsWith("+")) return " échec";
  return "";
}

// ── Surbrillance cases livre (mousedown/mouseup) ──────────────────────────────

function exHighlightSquares(uci) {
  exClearHint();
  if (!uci || uci.length < 4) return;
  const files = "abcdefgh";
  const sqFrom = document.getElementById(`ex-sq-${files.indexOf(uci[0])}-${parseInt(uci[1])-1}`);
  const sqTo   = document.getElementById(`ex-sq-${files.indexOf(uci[2])}-${parseInt(uci[3])-1}`);
  if (sqFrom) sqFrom.classList.add("ex-hint");
  if (sqTo)   sqTo.classList.add("ex-hint");
}

function exClearHint() {
  document.querySelectorAll(".ex-hint").forEach(sq => sq.classList.remove("ex-hint"));
}

function exSetSyncBtn(enabled) {
  const btn = document.getElementById("ex-btn-sync");
  if (!btn) return;
  btn.disabled  = !enabled;
  btn.style.opacity = enabled ? "1" : "0.4";
  btn.style.cursor  = enabled ? "pointer" : "not-allowed";
}

function exSetInstructions(msg) {
  const el = document.getElementById("ex-run-instructions");
  if (el) el.innerHTML = msg;
}

function exSetFeedback(msg, color, duration = 4000) {
  const fb = document.getElementById("ex-feedback");
  if (!fb) return;
  fb.textContent    = msg;
  fb.style.color    = "#fff";
  fb.style.background = color;
  fb.style.display  = "block";
  if (duration > 0) setTimeout(() => { fb.style.display = "none"; }, duration);
}

// ── Handlers socket exercices ─────────────────────────────────────────────────

socket.on("exercice_init", (data) => {
  // Cacher spinner, montrer échiquier
  const spinner = document.getElementById("ex-spinner");
  const wrapper = document.getElementById("ex-board-wrapper");
  if (spinner) spinner.style.display = "none";
  if (wrapper) wrapper.style.display = "flex";
  exBuildBoard();
  const o = data.ouverture;
  const nomEl = document.getElementById("ex-run-nom");
  if (nomEl) nomEl.textContent = `${o.eco} — ${o.nom}`;
  const varEl = document.getElementById("ex-run-variete");
  if (varEl) varEl.textContent = `Variété adversaire : ${data.variete} réponse${data.variete > 1 ? "s" : ""}`;
  const topEl = document.getElementById("ex-player-top");
  const botEl = document.getElementById("ex-player-bottom");
  if (data.human_color === "white") {
    if (topEl) topEl.textContent = "Adversaire (livre)";
    if (botEl) botEl.textContent = "Vous (Blancs)";
  } else {
    if (topEl) topEl.textContent = "Vous (Noirs)";
    if (botEl) botEl.textContent = "Adversaire (livre)";
  }
  const statusEl = document.getElementById("ex-run-status");
  if (statusEl) { statusEl.textContent = "Placez les pièces…"; statusEl.style.color = "#ff9800"; }
  const infoEl = document.getElementById("ex-run-info");
  if (infoEl) infoEl.textContent = o.desc;
  // Instructions initiales
  exSetSyncBtn(true);
  exSetInstructions(
    "① Reproduisez la position sur le plateau physique<br>" +
    "② Cliquez <b>Synchroniser</b> pour démarrer<br>" +
    "③ Jouez vos coups — le livre répond automatiquement<br>" +
    "<span style='color:#ff9800;'>Si vous vous trompez : replacez la pièce et recliquez Synchroniser</span>"
  );
});

socket.on("exercice_position", (data) => {
  exRenderBoard(data.fen, data.from, data.to);
  const movesEl = document.getElementById("ex-run-moves-count");
  if (movesEl) movesEl.textContent = `Coup ${data.move_num}`;
  const statusEl = document.getElementById("ex-run-status");
  if (statusEl) {
    statusEl.textContent = data.human_turn ? "À votre tour" : "Adversaire réfléchit…";
    statusEl.style.color = data.human_turn ? "#e0e0e0" : "#aaa";
  }
  // Afficher les coups du livre traduits avec surbrillance mousedown
  const bookEl = document.getElementById("ex-run-book-moves");
  if (bookEl && data.book_moves && data.book_moves.length > 0) {
    bookEl.innerHTML = "";
    data.book_moves.forEach((m, i) => {
      const span = document.createElement("span");
      const fr = sanToFr(m.san || m);
      span.textContent = (i === 0 ? "★ " : "  ") + fr;
      span.style.color  = i === 0 ? "#4caf50" : "#778";
      span.style.cursor = "pointer";
      span.style.userSelect = "none";
      span.title = m.uci || "";
      if (m.uci) {
        span.addEventListener("mousedown",  (e) => { e.preventDefault(); exHighlightSquares(m.uci); });
        span.addEventListener("mouseup",    ()  => exClearHint());
        span.addEventListener("mouseleave", ()  => exClearHint());
      }
      bookEl.appendChild(span);
      bookEl.appendChild(document.createElement("br"));
    });
  } else if (bookEl) {
    bookEl.innerHTML = '<span style="color:#556;">Fin de la théorie</span>';
  }
});

socket.on("exercice_wait_position", (data) => {
  _exOutOfBook = false;
  exRenderBoard(data.fen, null, null);
  const statusEl = document.getElementById("ex-run-status");
  if (statusEl) {
    statusEl.textContent = `Reproduisez la position de départ (${data.move_count} coup${data.move_count > 1 ? "s" : ""} joués)`;
    statusEl.style.color = "#ff9800";
  }
  exSetSyncBtn(true);
});

let _exOutOfBook = false;  // true = bip déjà émis, bloquer les répétitions

socket.on("exercice_move_ok", (data) => {
  _exOutOfBook = false;
  const rank = data.rank === 1 ? "★ Coup principal !" : `Coup théorique (${data.rank}/${data.total})`;
  const color = data.rank === 1 ? "#4caf50" : "#2196f3";
  exSetFeedback(`✓ ${sanToFr(data.san)} — ${rank}`, color, 2500);
});

socket.on("exercice_out_of_book", (data) => {
  if (!_exOutOfBook) { playBeep(); _exOutOfBook = true; }
  const moves = data.valid_moves || (data.valid_sans || []).map(s => ({ san: s, uci: "" }));
  const validList = moves.length
    ? ` — Coups valides : ${moves.map(m => sanToFr(m.san)).join(", ")}`
    : ` — Coup recommandé : ${sanToFr(data.best_san)}`;
  exSetFeedback(`✗ ${sanToFr(data.san)} — Hors théorie !${validList}`, "#e94560", 0);
  const statusEl = document.getElementById("ex-run-status");
  if (statusEl) { statusEl.textContent = "✗ Hors théorie — replacez la pièce"; statusEl.style.color = "#e94560"; }
  // Afficher dans le panel coups du livre avec surbrillance mousedown
  const bookEl = document.getElementById("ex-run-book-moves");
  if (bookEl && moves.length) {
    bookEl.innerHTML = "";
    const title = document.createElement("div");
    title.style.cssText = "color:#e94560;margin-bottom:4px;";
    title.textContent = "Coups théoriques :";
    bookEl.appendChild(title);
    moves.forEach((m, i) => {
      const span = document.createElement("span");
      span.textContent = (i === 0 ? "★ " : "  ") + sanToFr(m.san);
      span.style.color  = i === 0 ? "#4caf50" : "#778";
      span.style.cursor = "pointer";
      span.style.userSelect = "none";
      if (m.uci) {
        span.addEventListener("mousedown",  (e) => { e.preventDefault(); exHighlightSquares(m.uci); });
        span.addEventListener("mouseup",    ()  => exClearHint());
        span.addEventListener("mouseleave", ()  => exClearHint());
      }
      bookEl.appendChild(span);
      bookEl.appendChild(document.createElement("br"));
    });
  }
});

socket.on("exercice_adv_move", (data) => {
  exSetFeedback(`Adversaire : ${sanToFr(data.san)}`, "#aac4e0", 2000);
});

socket.on("exercice_synced", (data) => {
  const statusEl = document.getElementById("ex-run-status");
  if (statusEl) { statusEl.textContent = "✓ Synchronisé — à votre tour"; statusEl.style.color = "#4caf50"; }
  exSetFeedback("✓ Plateau synchronisé — jouez !", "#4caf50", 2500);
  exSetSyncBtn(false);
  exSetInstructions(
    "✓ Synchronisé ! Jouez votre coup sur le plateau.<br>" +
    "<span style='color:#aaa;'>Le bouton Synchroniser se réactivera après chaque coup adversaire si besoin.</span>"
  );
});

socket.on("exercice_sync_error", (data) => {
  exSetFeedback(`⚠ ${data.message}`, "#e94560", 0);
  const statusEl = document.getElementById("ex-run-status");
  if (statusEl) { statusEl.textContent = "⚠ Position incorrecte"; statusEl.style.color = "#e94560"; }
  exSetSyncBtn(true);
});

socket.on("exercice_end_of_line", (data) => {
  const nbCoups = Math.floor(data.moves / 2);
  exSetFeedback(`🎉 Ligne complète ! ${nbCoups} coup${nbCoups > 1 ? "s" : ""} de théorie maîtrisés`, "#4caf50", 0);
  const statusEl = document.getElementById("ex-run-status");
  if (statusEl) { statusEl.textContent = "🎉 Ligne terminée !"; statusEl.style.color = "#4caf50"; }
  exSetSyncBtn(false);
  exSetInstructions(
    "🎉 <b>Bravo !</b> Vous avez complété la ligne théorique.<br>" +
    "Cliquez <b>Recommencer</b> pour rejouer ou choisissez une autre ouverture."
  );
});

socket.on("exercice_back", () => {
  // Retour à l'écran de sélection — déjà géré par app_state
});

socket.on("position_error", (data) => {
  const exScreen = document.getElementById("screen-exercice-running");
  if (exScreen && exScreen.style.display !== "none") {
    // Exercice : pas de cases rouges — les LEDs suffisent
    return;
  }
  const laboScreen = document.getElementById("screen-labo");
  if (laboScreen && laboScreen.style.display !== "none") {
    laboRenderBoardWithErrors(data.expected_fen, data.physical_fen);
  } else {
    renderBoardWithErrors(data.expected_fen, data.physical_fen);
  }
});

buildBoard();
_buildBoardPosInit();
renderBoard(currentFen, null, null, null, null, null, null);
// Griser les contrôles nav au démarrage (pas de partie chargée)
_setNavControls(false);
