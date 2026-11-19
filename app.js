(function () {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    tg.ready();
    tg.expand();
  }

  const params = new URLSearchParams(window.location.search);
  const isSubdirViewer =
    window.location.pathname.includes("/viewer/") ||
    window.location.pathname.endsWith("/viewer");
  const rootPrefix = isSubdirViewer ? ".." : ".";
  const iconsBase = `${rootPrefix}/icons`;
  const dataBase = `${rootPrefix}/data`;

  // DOM refs
  const stateScreen = document.getElementById("state-screen");
  const stateSpinner = document.getElementById("state-spinner");
  const stateTitle = document.getElementById("state-title");
  const stateMessage = document.getElementById("state-message");
  const manualForm = document.getElementById("manual-load-form");
  const manualInput = document.getElementById("manual-replay-id");
  const retryBtn = document.getElementById("retry-btn");
  const viewerMain = document.getElementById("viewer-main");

  const mapNameEl = document.getElementById("map-name");
  const matchMetaSubEl = document.getElementById("match-meta-sub");
  const replayIdBadgeEl = document.getElementById("replay-id-badge");
  const playersBarEl = document.getElementById("players-bar");

  const timelineSlider = document.getElementById("timeline-slider");
  const battleMarkersEl = document.getElementById("battle-markers");
  const playPauseBtn = document.getElementById("play-pause-btn");
  const timeDisplayEl = document.getElementById("time-display");
  const hudTimeEl = document.getElementById("hud-time");
  const hudUnitsEl = document.getElementById("hud-units-count");
  const unitTooltipEl = document.getElementById("unit-tooltip");

  const zoomInBtn = document.getElementById("zoom-in-btn");
  const zoomOutBtn = document.getElementById("zoom-out-btn");
  const zoomResetBtn = document.getElementById("zoom-reset-btn");
  const toggleIconsBtn = document.getElementById("toggle-icons-btn");

  const buildPlayerFiltersEl = document.getElementById("build-player-filters");
  const buildOrderListEl = document.getElementById("build-order-list");
  const battlesListEl = document.getElementById("battles-list");

  let currentReplayId = null;
  let currentData = null;
  let buildFilterPid = "all";
  let buildFilterKind = "all";
  let tooltipTimer = null;

  const player = new window.ReplayPlayer(document.getElementById("map-canvas"), {
    iconsBase,
    onTimeUpdate: (cur, dur, unitCount) => {
      const curStr = formatTime(Math.floor(cur));
      const durStr = formatTime(Math.floor(dur));
      timelineSlider.value = String(cur);
      timeDisplayEl.textContent = `${curStr} / ${durStr}`;
      hudTimeEl.textContent = curStr;
      hudUnitsEl.textContent = `${unitCount} юнитов`;
    },
    onPlayStateChange: (playing) => {
      playPauseBtn.textContent = playing ? "⏸" : "▶";
    },
    onUnitSelect: (unit) => {
      if (tooltipTimer) clearTimeout(tooltipTimer);
      if (!unit) {
        unitTooltipEl.classList.add("hidden");
        return;
      }
      unitTooltipEl.textContent = `${unit.unitName} • ${unit.playerName}`;
      unitTooltipEl.classList.remove("hidden");
      tooltipTimer = setTimeout(() => unitTooltipEl.classList.add("hidden"), 2500);
    },
  });

  function formatTime(totalSec) {
    const s = Math.max(0, Math.floor(totalSec || 0));
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function resolveReplayId() {
    const fromTg = tg?.initDataUnsafe?.start_param;
    const fromUrl =
      params.get("startapp") ||
      params.get("tgWebAppStartParam") ||
      params.get("id") ||
      params.get("replay");
    return (fromTg || fromUrl || "").trim();
  }

  function inferGitHubConfig() {
    const repoParam = params.get("repo");
    const branch = params.get("branch") || "gh-pages";
    const prefix = (params.get("prefix") || "data").replace(/^\/+|\/+$/g, "");
    if (repoParam && repoParam.includes("/")) {
      return { repo: repoParam, branch, prefix };
    }
    const host = window.location.hostname;
    if (host.endsWith(".github.io")) {
      const owner = host.split(".")[0];
      const segs = window.location.pathname.split("/").filter(Boolean);
      if (segs.length > 0) {
        return { repo: `${owner}/${segs[0]}`, branch, prefix };
      }
    }
    return null;
  }

  function buildJsonCandidates(replayId) {
    const explicitJson = params.get("json");
    if (explicitJson) return [explicitJson];

    const candidates = [`${dataBase}/replays/${encodeURIComponent(replayId)}.json`];
    const gh = inferGitHubConfig();
    if (gh) {
      const path = gh.prefix
        ? `${gh.prefix}/replays/${encodeURIComponent(replayId)}.json`
        : `replays/${encodeURIComponent(replayId)}.json`;
      candidates.push(`https://raw.githubusercontent.com/${gh.repo}/${gh.branch}/${path}`);
    }
    return candidates;
  }

  function buildMinimapCandidates(filename) {
    if (!filename) return [];
    const candidates = [`${dataBase}/minimaps/${encodeURIComponent(filename)}`];
    const gh = inferGitHubConfig();
    if (gh) {
      const path = gh.prefix
        ? `${gh.prefix}/minimaps/${encodeURIComponent(filename)}`
        : `minimaps/${encodeURIComponent(filename)}`;
      candidates.push(`https://raw.githubusercontent.com/${gh.repo}/${gh.branch}/${path}`);
    }
    return candidates;
  }

  async function fetchJsonWithFallback(urls) {
    let lastErr = null;
    for (const url of urls) {
      try {
        const resp = await fetch(url, { cache: "no-cache" });
        if (!resp.ok) {
          lastErr = new Error(`HTTP ${resp.status} (${url})`);
          continue;
        }
        return await resp.json();
      } catch (err) {
        lastErr = err;
      }
    }
    throw lastErr || new Error("Не удалось загрузить JSON реплея");
  }

  function loadImageWithFallback(urls) {
    return new Promise((resolve) => {
      if (!urls.length) {
        resolve(null);
        return;
      }
      let idx = 0;
      const tryNext = () => {
        if (idx >= urls.length) {
          resolve(null);
          return;
        }
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = () => resolve(img);
        img.onerror = () => {
          idx += 1;
          tryNext();
        };
        img.src = urls[idx];
      };
      tryNext();
    });
  }

  function showLoading(title, msg) {
    viewerMain.classList.add("hidden");
    stateScreen.classList.remove("hidden");
    stateSpinner.classList.remove("hidden");
    manualForm.classList.add("hidden");
    retryBtn.classList.add("hidden");
    stateTitle.textContent = title;
    stateMessage.textContent = msg;
  }

  function showEmptyOrError(title, msg, allowRetry = false) {
    viewerMain.classList.add("hidden");
    stateScreen.classList.remove("hidden");
    stateSpinner.classList.add("hidden");
    manualForm.classList.remove("hidden");
    retryBtn.classList.toggle("hidden", !allowRetry);
    stateTitle.textContent = title;
    stateMessage.textContent = msg;
  }

  async function loadReplay(replayId) {
    currentReplayId = replayId;
    if (!replayId && !params.get("json")) {
      showEmptyOrError(
        "SC2GG Replay Viewer",
        "Откройте реплей через кнопку в Telegram-боте или введите Replay ID вручную."
      );
      return;
    }

    showLoading("Загрузка реплея...", `Матч #${replayId || "local"}`);
    try {
      const data = await fetchJsonWithFallback(buildJsonCandidates(replayId));
      const minimapImg = await loadImageWithFallback(
        buildMinimapCandidates(data.meta?.minimap_filename)
      );

      currentData = data;
      renderAll(data, minimapImg);

      stateScreen.classList.add("hidden");
      viewerMain.classList.remove("hidden");
      player.resize();
    } catch (err) {
      showEmptyOrError(
        "Реплей не найден",
        `Не удалось загрузить данные (${err.message}). Если реплей только что загружен, подождите 20–30 сек и нажмите «Повторить».`,
        true
      );
    }
  }

  function renderAll(data, minimapImg) {
    // Header
    mapNameEl.textContent = data.meta?.map_name || "Unknown Map";
    matchMetaSubEl.textContent = `${formatTime(data.meta?.duration_sec)} • v${data.meta?.version || "?"}`;
    replayIdBadgeEl.textContent = `#${data.meta?.replay_id || ""}`;

    // Players
    playersBarEl.innerHTML = (data.players || [])
      .map((p) => {
        const resLower = (p.result || "").toLowerCase();
        const resClass = resLower === "win" ? "win" : "loss";
        const resLabel = resLower === "win" ? "WIN" : "LOSS";
        const raceIcon = `${iconsBase}/races/${encodeURIComponent(p.race)}Icon.png`;
        return `
          <div class="player-card" style="border-left-color: ${escapeHtml(p.color_hex || "#fff")}">
            <div class="player-top">
              <img class="race-icon" src="${raceIcon}" alt="${escapeHtml(p.race)}" onerror="this.style.display='none'" />
              <span class="player-name">${escapeHtml(p.name)}</span>
              <span class="result-pill ${resClass}">${resLabel}</span>
            </div>
            <div class="player-stats">
              <span>APM ${p.apm || 0}</span>
              <span>Раб. ${p.workers_peak || 0}</span>
              <span>Армия ${(p.army_value_peak || 0).toLocaleString("ru-RU")}</span>
            </div>
          </div>
        `;
      })
      .join("");

    // Timeline slider & battle markers
    const dur = Math.max(1, data.meta?.duration_sec || 1);
    timelineSlider.max = String(dur);
    timelineSlider.value = "0";
    battleMarkersEl.innerHTML = (data.battles || [])
      .map((b) => {
        const pct = Math.max(0, Math.min(100, (b.start_sec / dur) * 100));
        return `<span class="battle-marker-dot" style="left:${pct}%" title="Битва ${formatTime(b.start_sec)}"></span>`;
      })
      .join("");

    // Set player data
    player.setData(data, minimapImg);

    // Build Order filters & list
    renderBuildFilters(data.players || []);
    renderBuildOrder();

    // Battles
    renderBattles(data);

    // Charts (rendered on tab open or right away)
    renderCharts(data);
  }

  function renderBuildFilters(players) {
    const btns = [`<button class="chip active" data-pid="all">Оба игрока</button>`];
    for (const p of players) {
      btns.push(
        `<button class="chip" data-pid="${p.pid}">${escapeHtml(p.name)}</button>`
      );
    }
    buildPlayerFiltersEl.innerHTML = btns.join("");
    buildFilterPid = "all";

    buildPlayerFiltersEl.querySelectorAll(".chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        buildPlayerFiltersEl.querySelectorAll(".chip").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        buildFilterPid = btn.dataset.pid;
        renderBuildOrder();
      });
    });
  }

  function renderBuildOrder() {
    if (!currentData) return;
    const playersById = new Map((currentData.players || []).map((p) => [p.pid, p]));
    const items = (currentData.build_order || []).filter((item) => {
      if (buildFilterPid !== "all" && String(item.pid) !== buildFilterPid) return false;
      if (buildFilterKind !== "all" && item.kind !== buildFilterKind) return false;
      return true;
    });

    if (!items.length) {
      buildOrderListEl.innerHTML = `<div class="muted" style="padding:12px;text-align:center;">Нет событий по выбранному фильтру</div>`;
      return;
    }

    buildOrderListEl.innerHTML = items
      .map((item) => {
        const p = playersById.get(item.pid);
        const color = p?.color_hex || "#fff";
        const iconHtml =
          item.kind === "upgrade"
            ? `<div class="unit-thumb" style="display:flex;align-items:center;justify-content:center;font-size:14px;">⚡</div>`
            : `<img class="unit-thumb" src="${window.resolveUnitIconPath(item.name, iconsBase)}" alt="" onerror="this.style.visibility='hidden'" />`;
        return `
          <div class="build-item" data-time="${item.time_sec}">
            <span class="build-time">${formatTime(item.time_sec)}</span>
            <span class="player-dot" style="background:${escapeHtml(color)}"></span>
            ${iconHtml}
            <div class="build-info">
              <div class="build-name">${escapeHtml(item.name)}</div>
              <div class="build-kind">${escapeHtml(p?.name || `P${item.pid}`)} • ${escapeHtml(item.kind)}</div>
            </div>
          </div>
        `;
      })
      .join("");

    buildOrderListEl.querySelectorAll(".build-item").forEach((el) => {
      el.addEventListener("click", () => {
        const t = Number(el.dataset.time) || 0;
        switchTab("map");
        player.seek(t);
      });
    });
  }

  function renderBattles(data) {
    const battles = data.battles || [];
    if (!battles.length) {
      battlesListEl.innerHTML = `<div class="muted" style="padding:20px;text-align:center;">Крупных сражений не зафиксировано</div>`;
      return;
    }

    const players = data.players || [];
    battlesListEl.innerHTML = battles
      .map((b, idx) => {
        const sidesHtml = players
          .map((p) => {
            const lostMin = b.lost_minerals?.[p.pid] || 0;
            const lostGas = b.lost_gas?.[p.pid] || 0;
            const unitsObj = b.units_lost?.[p.pid] || {};
            const isWinner = b.winner_pid === p.pid;
            const unitsHtml = Object.entries(unitsObj)
              .map(([uName, count]) => {
                const iconSrc = window.resolveUnitIconPath(uName, iconsBase);
                return `
                  <span class="lost-unit-chip" title="${escapeHtml(uName)}">
                    <img src="${iconSrc}" alt="" onerror="this.style.display='none'" />
                    <span>${escapeHtml(uName)} ×${count}</span>
                  </span>
                `;
              })
              .join("");

            return `
              <div class="battle-side" style="border-top: 2px solid ${escapeHtml(p.color_hex || "#fff")}">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                  <strong>${escapeHtml(p.name)}</strong>
                  ${isWinner ? '<span class="result-pill win">WIN</span>' : ""}
                </div>
                <div class="battle-losses">Потери: ${lostMin} мин / ${lostGas} газ</div>
                <div class="lost-units-row">${unitsHtml || '<span class="muted">Без потерь</span>'}</div>
              </div>
            `;
          })
          .join("");

        return `
          <div class="battle-card">
            <div class="battle-header">
              <span class="battle-time">⚔️ Битва #${idx + 1} • ${formatTime(b.start_sec)} – ${formatTime(b.end_sec)}</span>
              <button class="btn btn-primary jump-battle-btn" data-time="${Math.max(0, b.start_sec - 3)}">▶ На карте</button>
            </div>
            <div class="battle-players">${sidesHtml}</div>
          </div>
        `;
      })
      .join("");

    battlesListEl.querySelectorAll(".jump-battle-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const t = Number(btn.dataset.time) || 0;
        switchTab("map");
        player.seek(t);
        player.play();
      });
    });
  }

  function renderCharts(data) {
    const charts = data.charts;
    if (!charts || !charts.times_sec?.length) return;
    const players = data.players || [];

    drawLineChart("chart-army", charts.times_sec, charts.army_value, players);
    drawLineChart("chart-workers", charts.times_sec, charts.workers, players);
    drawLineChart("chart-supply", charts.times_sec, charts.supply_used, players);
    drawLineChart("chart-unspent", charts.times_sec, charts.unspent_resources, players);
  }

  function drawLineChart(canvasId, times, seriesByPid, players) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const w = rect.width || 320;
    const h = rect.height || 180;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = w * dpr;
    canvas.height = h * dpr;

    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const padL = 42;
    const padR = 10;
    const padT = 16;
    const padB = 22;
    const plotW = Math.max(10, w - padL - padR);
    const plotH = Math.max(10, h - padT - padB);

    let maxVal = 1;
    for (const p of players) {
      const arr = seriesByPid?.[p.pid] || [];
      for (const v of arr) {
        if (v > maxVal) maxVal = v;
      }
    }

    // Grid
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.fillStyle = "#8b9bb4";
    ctx.font = "10px sans-serif";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padT + (plotH * i) / 4;
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(w - padR, y);
      ctx.stroke();
      const val = Math.round(maxVal * (1 - i / 4));
      ctx.fillText(val >= 1000 ? `${(val / 1000).toFixed(1)}k` : String(val), 4, y + 3);
    }

    const maxTime = times[times.length - 1] || 1;
    for (let i = 0; i <= 4; i++) {
      const t = Math.round((maxTime * i) / 4);
      const x = padL + (plotW * i) / 4;
      ctx.fillText(formatTime(t), Math.min(w - 30, Math.max(padL, x - 12)), h - 6);
    }

    // Series
    for (const p of players) {
      const arr = seriesByPid?.[p.pid] || [];
      if (!arr.length) continue;
      ctx.beginPath();
      ctx.strokeStyle = p.color_hex || "#3b82f6";
      ctx.lineWidth = 2;
      for (let i = 0; i < arr.length; i++) {
        const x = padL + (times[i] / maxTime) * plotW;
        const y = padT + plotH - (arr[i] / maxVal) * plotH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
  }

  function switchTab(tabName) {
    document.querySelectorAll(".tab-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === tabName);
    });
    document.querySelectorAll(".tab-panel").forEach((p) => {
      p.classList.toggle("active", p.id === `tab-${tabName}`);
    });
    if (tabName === "map") {
      player.resize();
    } else if (tabName === "charts" && currentData) {
      renderCharts(currentData);
    }
  }

  // Event bindings
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  playPauseBtn.addEventListener("click", () => player.togglePlay());

  timelineSlider.addEventListener("input", (e) => {
    player.seek(Number(e.target.value));
  });

  document.querySelectorAll(".speed-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".speed-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      player.setSpeed(Number(btn.dataset.speed));
    });
  });

  zoomInBtn.addEventListener("click", () => player.zoomBy(1.3));
  zoomOutBtn.addEventListener("click", () => player.zoomBy(1 / 1.3));
  zoomResetBtn.addEventListener("click", () => player.resetView());
  toggleIconsBtn.addEventListener("click", () => {
    const next = !toggleIconsBtn.classList.contains("active");
    toggleIconsBtn.classList.toggle("active", next);
    player.setShowIcons(next);
  });

  document.querySelectorAll("[data-kind]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-kind]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      buildFilterKind = btn.dataset.kind;
      renderBuildOrder();
    });
  });

  manualForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const id = manualInput.value.trim();
    if (id) loadReplay(id);
  });

  retryBtn.addEventListener("click", () => loadReplay(currentReplayId));

  // Initial load
  loadReplay(resolveReplayId());
})();
