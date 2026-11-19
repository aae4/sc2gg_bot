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
  const timelineDiffCanvas = document.getElementById("timeline-diff-canvas");
  const battleMarkersEl = document.getElementById("battle-markers");
  const battleMarkerTooltipEl = document.getElementById("battle-marker-tooltip");
  const prevBattleBtn = document.getElementById("prev-battle-btn");
  const seekBackBtn = document.getElementById("seek-back-btn");
  const playPauseBtn = document.getElementById("play-pause-btn");
  const seekFwdBtn = document.getElementById("seek-fwd-btn");
  const nextBattleBtn = document.getElementById("next-battle-btn");
  const timeDisplayEl = document.getElementById("time-display");
  const hudTimeEl = document.getElementById("hud-time");
  const hudArmyCompareEl = document.getElementById("hud-army-compare");
  const battleHudEl = document.getElementById("battle-hud-overlay");
  const unitTooltipEl = document.getElementById("unit-tooltip");

  const zoomInBtn = document.getElementById("zoom-in-btn");
  const zoomOutBtn = document.getElementById("zoom-out-btn");
  const zoomResetBtn = document.getElementById("zoom-reset-btn");
  const toggleIconsBtn = document.getElementById("toggle-icons-btn");
  const toggleBattleHudBtn = document.getElementById("toggle-battle-hud-btn");
  const toggleMapModeBtn = document.getElementById("toggle-map-mode-btn");

  const buildPlayerFiltersEl = document.getElementById("build-player-filters");
  const buildOrderListEl = document.getElementById("build-order-list");
  const battlesListEl = document.getElementById("battles-list");

  let currentReplayId = null;
  let currentData = null;
  let buildFilterPid = "all";
  let buildFilterKind = "all";
  let isScrubbing = false;
  let diffMetric = "army_value";
  let battleTooltipHideTimer = null;
  let lastBattleHudKey = "";
  let battleHudHelpOpen = false;
  let battleHudEnabled = (() => {
    try {
      const saved = window.localStorage.getItem("sc2gg_battle_hud");
      if (saved !== null) return saved === "1";
    } catch (_) {
      // ignore storage errors
    }
    return true;
  })();

  function setBattleHudEnabled(enabled) {
    battleHudEnabled = Boolean(enabled);
    if (toggleBattleHudBtn) {
      toggleBattleHudBtn.classList.toggle("active", battleHudEnabled);
      toggleBattleHudBtn.setAttribute("aria-pressed", battleHudEnabled ? "true" : "false");
    }
    try {
      window.localStorage.setItem("sc2gg_battle_hud", battleHudEnabled ? "1" : "0");
    } catch (_) {
      // ignore storage errors
    }
    lastBattleHudKey = "";
    if (!battleHudEnabled && battleHudEl) {
      battleHudEl.classList.add("hidden");
      lastBattleHudKey = "hidden";
    } else if (currentData) {
      updateBattleHud(player.currentTime || 0);
    }
  }

  if (toggleBattleHudBtn) {
    toggleBattleHudBtn.classList.toggle("active", battleHudEnabled);
    toggleBattleHudBtn.setAttribute("aria-pressed", battleHudEnabled ? "true" : "false");
  }

  function interpolateChartValue(times, values, timeSec) {
    if (!times?.length || !values?.length) return null;
    if (timeSec <= times[0]) return values[0] ?? null;
    const last = Math.min(times.length, values.length) - 1;
    if (last < 0) return null;
    if (timeSec >= times[last]) return values[last] ?? null;
    let lo = 0;
    let hi = last;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (times[mid] <= timeSec) lo = mid + 1;
      else hi = mid - 1;
    }
    const i0 = Math.max(0, hi);
    const i1 = Math.min(last, i0 + 1);
    if (values[i0] == null || values[i1] == null) return null;
    const dt = times[i1] - times[i0];
    const alpha = dt > 0 ? (timeSec - times[i0]) / dt : 0;
    return values[i0] + (values[i1] - values[i0]) * alpha;
  }

  function renderHudCompare(timeSec, statsByPid) {
    const players = currentData?.players || [];
    if (!players.length) {
      hudArmyCompareEl.classList.add("hidden");
      return;
    }
    const times = currentData?.charts?.times_sec;
    const armySeries = currentData?.charts?.army_value;

    const parts = players.map((p) => {
      const st = statsByPid?.[p.pid] || { workers: 0, army: 0 };
      const val = interpolateChartValue(times, armySeries?.[p.pid], timeSec);
      const valStr =
        val !== null
          ? ` (${val >= 1000 ? `${(val / 1000).toFixed(1)}k` : Math.round(val)})`
          : "";
      return `
        <span class="hud-player-stat">
          <span class="player-dot" style="background:${escapeHtml(p.color_hex || "#fff")}"></span>
          <span>${st.workers}р • ${st.army}а${valStr}</span>
        </span>
      `;
    });

    hudArmyCompareEl.innerHTML = parts.join(`<span class="hud-vs">vs</span>`);
    hudArmyCompareEl.classList.remove("hidden");
  }

  function renderInspector(selection) {
    if (!selection) {
      unitTooltipEl.classList.add("hidden");
      unitTooltipEl.innerHTML = "";
      return;
    }

    if (selection.type === "unit") {
      const { unit, ranges, squad } = selection;
      const atkText = ranges.attack > 0.5 ? `<span>🎯 Атака: ${ranges.attack}</span>` : "";
      const sightText = ranges.sight > 0 ? `<span>👁 Обзор: ${ranges.sight}</span>` : "";
      const totalNearby = squad.reduce((acc, [, cnt]) => acc + cnt, 0);
      const squadHtml =
        totalNearby > 1
          ? `<div class="inspector-squad">${squad
              .map(([name, cnt]) => `<span class="squad-chip">${escapeHtml(name)} ×${cnt}</span>`)
              .join("")}</div>`
          : "";

      unitTooltipEl.innerHTML = `
        <div class="inspector-header">
          <div class="inspector-title">
            <span class="player-dot" style="background:${escapeHtml(unit.color)}"></span>
            <span>${escapeHtml(unit.unitName)} • ${escapeHtml(unit.playerName)}</span>
          </div>
          <button type="button" class="inspector-close" aria-label="Закрыть">×</button>
        </div>
        <div class="inspector-ranges">${sightText}${atkText}</div>
        ${squadHtml}
      `;
    } else if (selection.type === "area") {
      const summary = selection.groups
        .map(
          (g) =>
            `<span class="hud-player-stat"><span class="player-dot" style="background:${escapeHtml(g.color)}"></span><span>${escapeHtml(g.playerName)}: ${g.total}</span></span>`
        )
        .join("");
      const chips = [];
      for (const g of selection.groups) {
        for (const [name, cnt] of g.units) {
          chips.push(`
            <span class="squad-chip">
              <span class="player-dot" style="background:${escapeHtml(g.color)}"></span>
              <span>${escapeHtml(name)} ×${cnt}</span>
            </span>
          `);
        }
      }
      unitTooltipEl.innerHTML = `
        <div class="inspector-header">
          <div class="inspector-title">🔍 Отряд в области</div>
          <button type="button" class="inspector-close" aria-label="Закрыть">×</button>
        </div>
        <div class="inspector-ranges">${summary}</div>
        <div class="inspector-squad">${chips.join("")}</div>
      `;
    }

    unitTooltipEl.classList.remove("hidden");
    const closeBtn = unitTooltipEl.querySelector(".inspector-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        player.clearSelection();
      });
    }
  }

  const player = new window.ReplayPlayer(document.getElementById("map-canvas"), {
    iconsBase,
    onTimeUpdate: (cur, dur, _unitCount, statsByPid) => {
      const curStr = formatTime(Math.floor(cur));
      const durStr = formatTime(Math.floor(dur));
      if (!isScrubbing) {
        timelineSlider.value = String(cur);
      }
      timeDisplayEl.textContent = `${curStr} / ${durStr}`;
      hudTimeEl.textContent = curStr;
      renderHudCompare(cur, statsByPid);
      updateBattleHud(cur);
      updateBattleNavButtons(cur);
    },
    onPlayStateChange: (playing) => {
      playPauseBtn.textContent = playing ? "⏸" : "▶";
    },
    onUnitSelect: (selection) => {
      renderInspector(selection);
    },
  });

  function getSortedBattles() {
    const battles = currentData?.battles || [];
    if (!battles.length) return [];
    return [...battles].sort((a, b) => (a.start_sec || 0) - (b.start_sec || 0));
  }

  function findPrevBattle(curTime) {
    const battles = getSortedBattles();
    for (let i = battles.length - 1; i >= 0; i -= 1) {
      const jumpTime = Math.max(0, (battles[i].start_sec || 0) - 3);
      if (jumpTime < curTime - 1.0) {
        return battles[i];
      }
    }
    return null;
  }

  function findNextBattle(curTime) {
    const battles = getSortedBattles();
    for (let i = 0; i < battles.length; i += 1) {
      const jumpTime = Math.max(0, (battles[i].start_sec || 0) - 3);
      if (jumpTime > curTime + 0.5) {
        return battles[i];
      }
    }
    return null;
  }

  function jumpToBattle(b) {
    if (!b) return;
    player.seek(Math.max(0, (b.start_sec || 0) - 3));
    player.focusOn(b.x, b.y, 3.0);
  }

  function updateBattleNavButtons(curTime) {
    if (prevBattleBtn) prevBattleBtn.disabled = !findPrevBattle(curTime);
    if (nextBattleBtn) nextBattleBtn.disabled = !findNextBattle(curTime);
  }

  function formatResourceValue(val) {
    const n = Number(val) || 0;
    if (n <= 0) return "0";
    if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
    return String(Math.round(n));
  }

  function findActiveBattle(curTime) {
    const battles = currentData?.battles;
    if (!battles || !battles.length) return null;

    let best = null;
    let bestInExactRange = false;
    let bestDist = Infinity;

    for (let idx = 0; idx < battles.length; idx += 1) {
      const b = battles[idx];
      const start = b.start_sec || 0;
      const end = b.end_sec || 0;
      if (curTime < start - 2 || curTime > end + 3) continue;

      const inExact = curTime >= start && curTime <= end;
      const mid = (start + end) * 0.5;
      const dist = Math.abs(curTime - mid);

      if (
        !best ||
        (inExact && !bestInExactRange) ||
        (inExact === bestInExactRange && dist < bestDist)
      ) {
        best = { battle: b, index: idx + 1 };
        bestInExactRange = inExact;
        bestDist = dist;
      }
    }
    return best;
  }

  function groupConsecutiveKills(deaths) {
    if (!deaths || !deaths.length) return [];
    const groups = [];
    for (const d of deaths) {
      const prev = groups[groups.length - 1];
      if (
        prev &&
        prev.killerPid === d.killerPid &&
        prev.killerTypeId === d.killerTypeId &&
        prev.victimPid === d.pid &&
        prev.victimTypeId === d.typeId
      ) {
        prev.count += 1;
        if (d.killerUid !== null && d.killerUid !== undefined) {
          prev.killerUids.add(d.killerUid);
        }
      } else {
        const killerUids = new Set();
        if (d.killerUid !== null && d.killerUid !== undefined) {
          killerUids.add(d.killerUid);
        }
        groups.push({
          killerPid: d.killerPid ?? null,
          killerTypeId: d.killerTypeId ?? null,
          victimPid: d.pid ?? null,
          victimTypeId: d.typeId ?? null,
          killerUids,
          count: 1,
        });
      }
    }
    return groups.slice(-4);
  }

  function updateBattleHud(curTime) {
    if (!battleHudEl) return;

    if (!battleHudEnabled) {
      if (lastBattleHudKey !== "hidden") {
        battleHudEl.classList.add("hidden");
        lastBattleHudKey = "hidden";
      }
      return;
    }

    const active = findActiveBattle(curTime);
    if (!active) {
      if (lastBattleHudKey !== "hidden") {
        battleHudEl.classList.add("hidden");
        lastBattleHudKey = "hidden";
      }
      return;
    }

    const { battle, index } = active;
    const winStart = (battle.start_sec || 0) - 1;
    const winEnd = Math.min(curTime, (battle.end_sec || 0) + 1);
    const deathsInWindow =
      typeof player._findDeathsInWindow === "function"
        ? player._findDeathsInWindow(winStart, winEnd)
        : [];

    const secKey = Math.floor(curTime);
    const cacheKey = `${index}|${secKey}|${deathsInWindow.length}|${battleHudHelpOpen ? 1 : 0}`;
    if (cacheKey === lastBattleHudKey) return;
    lastBattleHudKey = cacheKey;

    const lossByPid = new Map();
    for (const d of deathsInWindow) {
      if (d.pid === null || d.pid === undefined) continue;
      lossByPid.set(d.pid, (lossByPid.get(d.pid) || 0) + (d.value || 0));
    }

    const players = currentData?.players || [];
    const playersByPid = new Map(players.map((p) => [p.pid, p]));
    const totalLoss = players.reduce((sum, p) => sum + (lossByPid.get(p.pid) || 0), 0);

    const elapsedSec = Math.max(0, Math.floor(curTime - (battle.start_sec || 0)));
    const timerText = `длится ${formatTime(elapsedSec)}`;

    const sidesHtml = players
      .map((p) => {
        const loss = lossByPid.get(p.pid) || 0;
        const color = p.color_hex || "#94a3b8";
        const lossLabel = loss > 0 ? `−${formatResourceValue(loss)}` : "0";
        return `
          <span class="battle-hud-side">
            <span class="player-dot" style="background:${escapeHtml(color)}"></span>
            <span class="battle-hud-side-name">${escapeHtml(p.name || `P${p.pid}`)}</span>
            <span class="battle-hud-side-val">${lossLabel}</span>
          </span>
        `;
      })
      .join("");

    const barSegsHtml = players.length
      ? players
          .map((p) => {
            const loss = lossByPid.get(p.pid) || 0;
            const pct = totalLoss > 0 ? (loss / totalLoss) * 100 : 100 / players.length;
            const color = p.color_hex || "#94a3b8";
            return `<div class="battle-hud-bar-seg" style="width:${pct.toFixed(1)}%;background:${escapeHtml(color)}"></div>`;
          })
          .join("")
      : "";

    const unitDict = currentData?.unit_dict || {};
    const killGroups = groupConsecutiveKills(deathsInWindow);
    const feedHtml = killGroups.length
      ? `<div class="battle-hud-feed">${killGroups
          .map((g) => {
            const victimName = unitDict[g.victimTypeId] || "Unit";
            const victimIcon = window.resolveUnitIconPath(victimName, iconsBase);
            const victimColor = playersByPid.get(g.victimPid)?.color_hex || "#f1f5f9";
            const victimCnt = g.count > 1 ? ` ×${g.count}` : "";
            const victimChip = `
              <span class="battle-kill-unit" style="color:${escapeHtml(victimColor)}">
                <img class="battle-kill-icon" src="${victimIcon}" alt="" onerror="this.style.display='none'" />
                <span>${escapeHtml(victimName)}${victimCnt}</span>
              </span>
            `;

            const killerName = g.killerTypeId != null ? unitDict[g.killerTypeId] : null;
            if (!killerName) {
              return `<span class="battle-kill-chip">💀 ${victimChip}</span>`;
            }

            const killerIcon = window.resolveUnitIconPath(killerName, iconsBase);
            const killerColor = playersByPid.get(g.killerPid)?.color_hex || "#f1f5f9";
            const killerCnt = g.killerUids.size > 1 ? ` ×${g.killerUids.size}` : "";
            const killerChip = `
              <span class="battle-kill-unit" style="color:${escapeHtml(killerColor)}">
                <img class="battle-kill-icon" src="${killerIcon}" alt="" onerror="this.style.display='none'" />
                <span>${escapeHtml(killerName)}${killerCnt}</span>
              </span>
            `;
            return `<span class="battle-kill-chip">${killerChip}<span class="battle-kill-arrow">→ 💀</span>${victimChip}</span>`;
          })
          .join("")}</div>`
      : "";

    const helpHtml = battleHudHelpOpen
      ? `<div class="battle-hud-help">Потери ресурсов (минералы + газ) за текущий бой; полоса показывает долю потерь каждого игрока. Ниже — кто кого убил (💀).</div>`
      : "";

    battleHudEl.innerHTML = `
      <div class="battle-hud-header">
        <span class="battle-hud-title">⚔️ Битва #${index} <span class="battle-hud-sub">• Потери</span></span>
        <span class="battle-hud-right">
          <span class="battle-hud-timer">${timerText}</span>
          <button type="button" class="battle-hud-action" data-hud-action="help" title="Что это?" aria-label="Пояснение">?</button>
          <button type="button" class="battle-hud-action" data-hud-action="close" title="Скрыть сводку боя" aria-label="Скрыть">×</button>
        </span>
      </div>
      ${helpHtml}
      ${players.length ? `<div class="battle-hud-losses">${sidesHtml}</div>` : ""}
      ${barSegsHtml ? `<div class="battle-hud-bar ${totalLoss === 0 ? "is-empty" : ""}">${barSegsHtml}</div>` : ""}
      ${feedHtml}
    `;
    battleHudEl.classList.remove("hidden");
  }

  if (battleHudEl) {
    battleHudEl.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-hud-action]");
      if (!btn) return;
      e.stopPropagation();
      const action = btn.dataset.hudAction;
      if (action === "help") {
        battleHudHelpOpen = !battleHudHelpOpen;
        updateBattleHud(player.currentTime || 0);
      } else if (action === "close") {
        setBattleHudEnabled(false);
      }
    });
  }

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

  function buildHdMapCandidates(meta) {
    const candidates = [];
    const hdFile = meta?.hd_map_filename;
    if (hdFile) {
      candidates.push(`${iconsBase}/maps/${encodeURIComponent(hdFile)}`);
      candidates.push(`${dataBase}/minimaps/${encodeURIComponent(hdFile)}`);
      const gh = inferGitHubConfig();
      if (gh) {
        const path = gh.prefix
          ? `${gh.prefix}/minimaps/${encodeURIComponent(hdFile)}`
          : `minimaps/${encodeURIComponent(hdFile)}`;
        candidates.push(`https://raw.githubusercontent.com/${gh.repo}/${gh.branch}/${path}`);
      }
      return candidates;
    }

    const rawName = (meta?.map_name || "").trim();
    if (rawName) {
      const base = rawName.replace(/\s+(LE|TE|SE|CE|РВ)$/i, "").trim().replace(/\s+/g, "_");
      if (base) {
        candidates.push(`${iconsBase}/maps/${encodeURIComponent(base)}.jpg`);
      }
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
      const [minimapImg, hdMapImg] = await Promise.all([
        loadImageWithFallback(buildMinimapCandidates(data.meta?.minimap_filename)),
        loadImageWithFallback(buildHdMapCandidates(data.meta)),
      ]);

      currentData = data;
      renderAll(data, minimapImg, hdMapImg);

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

  function syncMapModeButton() {
    if (!toggleMapModeBtn) return;
    if (!player.hasHdMap()) {
      toggleMapModeBtn.classList.add("hidden");
      return;
    }
    toggleMapModeBtn.classList.remove("hidden");
    const isHd = player.mapMode === "hd";
    toggleMapModeBtn.classList.toggle("active", isHd);
    toggleMapModeBtn.textContent = isHd ? "HD" : "ТК";
    toggleMapModeBtn.title = isHd
      ? "Режим: HD-карта (нажмите для тактической схемы)"
      : "Режим: Тактическая схема (нажмите для HD-карты)";
  }

  function renderAll(data, minimapImg, hdMapImg) {
    lastBattleHudKey = "";
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
    hideBattleTooltip();

    const battles = data.battles || [];
    const players = data.players || [];
    const maxBattleLoss = Math.max(1, ...battles.map(getBattleTotalLoss));

    battleMarkersEl.innerHTML = battles
      .map((b, idx) => {
        const pct = Math.max(0, Math.min(100, (b.start_sec / dur) * 100));
        const jumpTime = Math.max(0, b.start_sec - 3);
        const bx = Number.isFinite(b.x) ? b.x : "";
        const by = Number.isFinite(b.y) ? b.y : "";
        const totalLoss = getBattleTotalLoss(b);
        const ratio = Math.sqrt(totalLoss / maxBattleLoss);
        const size = Math.round(6 + ratio * 7);
        const opacity = (0.5 + ratio * 0.5).toFixed(2);
        const glowAlpha = (0.45 + ratio * 0.5).toFixed(2);
        const glowRadius = Math.round(4 + ratio * 10);
        const lossesByPlayer = players.length
          ? players
              .map((p) => (b.lost_minerals?.[p.pid] || 0) + (b.lost_gas?.[p.pid] || 0))
              .join(" vs ")
          : String(totalLoss);
        const tooltipText = `⚔️ ${formatTime(b.start_sec)} • Потери: ${lossesByPlayer}`;
        const styleAttr = [
          `left:${pct}%`,
          `width:${size}px`,
          `height:${size}px`,
          `opacity:${opacity}`,
          `box-shadow:0 0 ${glowRadius}px rgba(239,68,68,${glowAlpha})`,
        ].join(";");
        return `<span class="battle-marker-dot" tabindex="0" style="${styleAttr}" data-pct="${pct}" data-time="${jumpTime}" data-x="${bx}" data-y="${by}" data-tooltip="${escapeHtml(tooltipText)}" aria-label="${escapeHtml(tooltipText)}"></span>`;
      })
      .join("");

    battleMarkersEl.querySelectorAll(".battle-marker-dot").forEach((dot) => {
      dot.addEventListener("mouseenter", () => showBattleTooltip(dot));
      dot.addEventListener("focus", () => showBattleTooltip(dot));
      dot.addEventListener("mouseleave", () => hideBattleTooltip());
      dot.addEventListener("blur", () => hideBattleTooltip());
      dot.addEventListener("click", (e) => {
        e.stopPropagation();
        showBattleTooltip(dot, true);
        const t = Number(dot.dataset.time) || 0;
        const bx = dot.dataset.x !== "" ? Number(dot.dataset.x) : NaN;
        const by = dot.dataset.y !== "" ? Number(dot.dataset.y) : NaN;
        player.seek(t);
        if (Number.isFinite(bx) && Number.isFinite(by)) {
          player.focusOn(bx, by, 3.0);
        }
      });
    });

    renderTimelineDiff();

    // Set player data
    player.setData(data, minimapImg, hdMapImg);
    syncMapModeButton();
    updateBattleNavButtons(0);

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

        const jumpTime = Math.max(0, b.start_sec - 3);
        const bx = Number.isFinite(b.x) ? b.x : "";
        const by = Number.isFinite(b.y) ? b.y : "";

        return `
          <div class="battle-card">
            <div class="battle-header">
              <span class="battle-time">⚔️ Битва #${idx + 1} • ${formatTime(b.start_sec)} – ${formatTime(b.end_sec)}</span>
              <button class="btn btn-primary jump-battle-btn" data-time="${jumpTime}" data-x="${bx}" data-y="${by}">▶ На карте</button>
            </div>
            <div class="battle-players">${sidesHtml}</div>
          </div>
        `;
      })
      .join("");

    battlesListEl.querySelectorAll(".jump-battle-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const t = Number(btn.dataset.time) || 0;
        const bx = btn.dataset.x !== "" ? Number(btn.dataset.x) : NaN;
        const by = btn.dataset.y !== "" ? Number(btn.dataset.y) : NaN;
        switchTab("map");
        player.seek(t);
        if (Number.isFinite(bx) && Number.isFinite(by)) {
          player.focusOn(bx, by, 3.0);
        }
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

  function getBattleTotalLoss(b) {
    const sumObj = (obj) =>
      Object.values(obj || {}).reduce((acc, v) => acc + (Number(v) || 0), 0);
    return sumObj(b?.lost_minerals) + sumObj(b?.lost_gas);
  }

  function showBattleTooltip(dot, autoHide = false) {
    if (!battleMarkerTooltipEl || !dot) return;
    if (battleTooltipHideTimer) {
      clearTimeout(battleTooltipHideTimer);
      battleTooltipHideTimer = null;
    }
    const text = dot.dataset.tooltip || "";
    if (!text) return;
    const pct = Number(dot.dataset.pct) || 0;
    battleMarkerTooltipEl.textContent = text;
    if (pct < 15) {
      battleMarkerTooltipEl.style.left = "0";
      battleMarkerTooltipEl.style.right = "auto";
      battleMarkerTooltipEl.style.transform = "none";
    } else if (pct > 85) {
      battleMarkerTooltipEl.style.left = "auto";
      battleMarkerTooltipEl.style.right = "0";
      battleMarkerTooltipEl.style.transform = "none";
    } else {
      battleMarkerTooltipEl.style.left = `${pct}%`;
      battleMarkerTooltipEl.style.right = "auto";
      battleMarkerTooltipEl.style.transform = "translateX(-50%)";
    }
    battleMarkerTooltipEl.classList.remove("hidden");

    if (autoHide) {
      battleTooltipHideTimer = setTimeout(() => {
        hideBattleTooltip();
      }, 2500);
    }
  }

  function hideBattleTooltip() {
    if (battleTooltipHideTimer) {
      clearTimeout(battleTooltipHideTimer);
      battleTooltipHideTimer = null;
    }
    if (battleMarkerTooltipEl) {
      battleMarkerTooltipEl.classList.add("hidden");
    }
  }

  function renderTimelineDiff() {
    if (!timelineDiffCanvas) return;
    const rect = timelineDiffCanvas.getBoundingClientRect();
    const w = rect.width || 300;
    const h = rect.height || 38;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    timelineDiffCanvas.width = Math.round(w * dpr);
    timelineDiffCanvas.height = Math.round(h * dpr);

    const ctx = timelineDiffCanvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const midY = h / 2;

    // Central parity axis
    ctx.beginPath();
    ctx.strokeStyle = "rgba(255, 255, 255, 0.16)";
    ctx.lineWidth = 1;
    ctx.moveTo(0, midY);
    ctx.lineTo(w, midY);
    ctx.stroke();

    const charts = currentData?.charts;
    const players = currentData?.players || [];
    const times = charts?.times_sec;
    if (!charts || !times?.length || players.length < 2) return;

    const series = charts[diffMetric];
    if (!series) return;

    const p1 = players[0];
    const p2 = players[1];
    const arr1 = series[p1.pid] || [];
    const arr2 = series[p2.pid] || [];
    if (!arr1.length && !arr2.length) return;

    const dur = Math.max(1, currentData.meta?.duration_sec || times[times.length - 1] || 1);
    const points = [];
    let maxAbsDiff = 1;

    for (let i = 0; i < times.length; i++) {
      const diff = (Number(arr1[i]) || 0) - (Number(arr2[i]) || 0);
      const absDiff = Math.abs(diff);
      if (absDiff > maxAbsDiff) maxAbsDiff = absDiff;
      points.push({
        x: Math.max(0, Math.min(w, (times[i] / dur) * w)),
        diff,
      });
    }

    const amp = Math.max(4, midY - 3);
    const coords = points.map((pt) => ({
      x: pt.x,
      y: midY - (pt.diff / maxAbsDiff) * amp,
    }));

    const traceArea = () => {
      ctx.beginPath();
      ctx.moveTo(coords[0].x, midY);
      for (const c of coords) {
        ctx.lineTo(c.x, c.y);
      }
      ctx.lineTo(coords[coords.length - 1].x, midY);
      ctx.closePath();
    };

    const traceCurve = () => {
      ctx.beginPath();
      coords.forEach((c, idx) => {
        if (idx === 0) ctx.moveTo(c.x, c.y);
        else ctx.lineTo(c.x, c.y);
      });
    };

    const p1Color = p1.color_hex || "#3b82f6";
    const p2Color = p2.color_hex || "#ef4444";

    // P1 advantage (above parity axis)
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, w, midY);
    ctx.clip();
    traceArea();
    ctx.globalAlpha = 0.32;
    ctx.fillStyle = p1Color;
    ctx.fill();
    traceCurve();
    ctx.globalAlpha = 0.85;
    ctx.strokeStyle = p1Color;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.restore();

    // P2 advantage (below parity axis)
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, midY, w, h - midY);
    ctx.clip();
    traceArea();
    ctx.globalAlpha = 0.32;
    ctx.fillStyle = p2Color;
    ctx.fill();
    traceCurve();
    ctx.globalAlpha = 0.85;
    ctx.strokeStyle = p2Color;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.restore();
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
      renderTimelineDiff();
    } else if (tabName === "charts" && currentData) {
      renderCharts(currentData);
    }
  }

  // Event bindings
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  playPauseBtn.addEventListener("click", () => player.togglePlay());
  if (seekBackBtn) {
    seekBackBtn.addEventListener("click", () => player.seek(player.currentTime - 5));
  }
  if (seekFwdBtn) {
    seekFwdBtn.addEventListener("click", () => player.seek(player.currentTime + 5));
  }
  if (prevBattleBtn) {
    prevBattleBtn.addEventListener("click", () => jumpToBattle(findPrevBattle(player.currentTime)));
  }
  if (nextBattleBtn) {
    nextBattleBtn.addEventListener("click", () => jumpToBattle(findNextBattle(player.currentTime)));
  }

  document.addEventListener("keydown", (e) => {
    if (!currentData) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const target = e.target;
    const tag = target && target.tagName ? target.tagName.toLowerCase() : "";
    if (tag === "input" || tag === "textarea" || tag === "select" || target?.isContentEditable) {
      return;
    }

    if (e.code === "Space" || e.key === " ") {
      e.preventDefault();
      player.togglePlay();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      player.seek(player.currentTime - 5);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      player.seek(player.currentTime + 5);
    }
  });

  timelineSlider.addEventListener("pointerdown", () => { isScrubbing = true; });
  timelineSlider.addEventListener("touchstart", () => { isScrubbing = true; }, { passive: true });
  const endScrub = () => { isScrubbing = false; };
  timelineSlider.addEventListener("pointerup", endScrub);
  timelineSlider.addEventListener("pointercancel", endScrub);
  timelineSlider.addEventListener("touchend", endScrub);
  timelineSlider.addEventListener("change", endScrub);
  timelineSlider.addEventListener("input", (e) => {
    player.seek(Number(e.target.value));
  });

  document.querySelectorAll(".diff-metric-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const nextMetric = btn.dataset.metric;
      if (!nextMetric) return;
      document.querySelectorAll(".diff-metric-btn").forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-pressed", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-pressed", "true");
      diffMetric = nextMetric;
      renderTimelineDiff();
    });
  });

  document.addEventListener("pointerdown", (e) => {
    if (!e.target.closest?.(".battle-marker-dot")) {
      hideBattleTooltip();
    }
  });

  document.querySelectorAll(".speed-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".speed-btn").forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-pressed", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-pressed", "true");
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
  if (toggleBattleHudBtn) {
    toggleBattleHudBtn.addEventListener("click", () => {
      setBattleHudEnabled(!battleHudEnabled);
    });
  }
  if (toggleMapModeBtn) {
    toggleMapModeBtn.addEventListener("click", () => {
      player.toggleMapMode();
      syncMapModeButton();
    });
  }

  document.querySelectorAll(".layer-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".layer-chip").forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-pressed", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-pressed", "true");
      player.setLayerFilter(btn.dataset.layer);
    });
  });

  let chartResizeTimer = null;
  let diffResizeTimer = null;
  window.addEventListener("resize", () => {
    if (!currentData) return;
    const mapTab = document.getElementById("tab-map");
    if (mapTab && mapTab.classList.contains("active")) {
      if (diffResizeTimer) clearTimeout(diffResizeTimer);
      diffResizeTimer = setTimeout(() => renderTimelineDiff(), 80);
    }
    const chartsTab = document.getElementById("tab-charts");
    if (chartsTab && chartsTab.classList.contains("active")) {
      if (chartResizeTimer) clearTimeout(chartResizeTimer);
      chartResizeTimer = setTimeout(() => renderCharts(currentData), 120);
    }
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
