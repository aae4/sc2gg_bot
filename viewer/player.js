(function (global) {
  "use strict";

  const UNIT_ICON_ALIASES = {
    siegetanksieged: "siegetank",
    supplydepotlowered: "supplydepot",
    vikingassault: "viking",
    vikingfighter: "vikingfighter",
    liberatorag: "liberator",
    lurkermp: "lurker",
    lurkermpburrowed: "lurker",
    widowmineburrowed: "widowmine",
    barracksreactor: "reactor",
    barrackstechlab: "techlab",
    factoryreactor: "reactor",
    factorytechlab: "techlab",
    starportreactor: "reactor",
    starporttechlab: "techlab",
    spinecrawleruprooted: "spinecrawler",
    sporecrawleruprooted: "sporecrawler",
    creeptumorburrowed: "creeptumor",
    creeptumorqueen: "creeptumor",
    overlordtransport: "overlord",
    warpprismphasing: "warpprism",
    observersiegemode: "observer",
    overseersiegemode: "overseer",
    commandcenterflying: "commandcenter",
    orbitalcommandflying: "orbitalcommand",
    barracksflying: "barracks",
    factoryflying: "factory",
    starportflying: "starport",
    helliontank: "hellbat",
    banelingburrowed: "baneling",
    roachburrowed: "roach",
    zerglingburrowed: "zergling",
    hydraliskburrowed: "hydralisk",
    infestorburrowed: "infestor",
    swarmhostmp: "swarmhost",
    swarmhostburrowedmp: "swarmhost",
    nyduscanal: "nydusworm",
    autoturret: "auto-turret",
    ravagercocoon: "ravager",
    banelingcocoon: "baneling",
    broodlordcocoon: "broodlord",
    overlordcocoon: "overseer",
    lurkeregg: "lurker",
    lurkermpegg: "lurker",
    transportoverlordcocoon: "overlord",
  };

  const BUILDING_NAMES = new Set([
    "CommandCenter", "OrbitalCommand", "PlanetaryFortress", "SupplyDepot", "SupplyDepotLowered",
    "Refinery", "Barracks", "EngineeringBay", "Bunker", "MissileTurret", "SensorTower",
    "Factory", "GhostAcademy", "Armory", "Starport", "FusionCore", "TechLab", "Reactor",
    "BarracksReactor", "BarracksTechLab", "FactoryReactor", "FactoryTechLab", "StarportReactor", "StarportTechLab",
    "Nexus", "Pylon", "Assimilator", "Gateway", "WarpGate", "Forge", "CyberneticsCore",
    "PhotonCannon", "ShieldBattery", "RoboticsFacility", "RoboticsBay", "Stargate", "FleetBeacon",
    "TwilightCouncil", "TemplarArchives", "DarkShrine",
    "Hatchery", "Lair", "Hive", "Extractor", "SpawningPool", "EvolutionChamber",
    "RoachWarren", "BanelingNest", "SpineCrawler", "SporeCrawler", "HydraliskDen",
    "LurkerDen", "LurkerDenMP", "InfestationPit", "Spire", "GreaterSpire", "NydusNetwork",
    "NydusWorm", "NydusCanal", "UltraliskCavern", "CreepTumor", "CreepTumorBurrowed", "CreepTumorQueen",
  ]);

  const WORKER_NAMES = new Set(["SCV", "Probe", "Drone"]);

  function resolveUnitIconPath(unitName, iconsBase) {
    const slug = String(unitName || "")
      .toLowerCase()
      .replace(/[^a-z0-9]/g, "");
    const mapped = UNIT_ICON_ALIASES[slug] || slug;
    return `${iconsBase}/units/${mapped}.jpg`;
  }

  class ReplayPlayer {
    constructor(canvas, options = {}) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.iconsBase = options.iconsBase || "./icons";
      this.onTimeUpdate = options.onTimeUpdate || (() => {});
      this.onPlayStateChange = options.onPlayStateChange || (() => {});
      this.onUnitSelect = options.onUnitSelect || (() => {});

      this.data = null;
      this.minimapImg = null;
      this.playersById = new Map();
      this.keyframeStates = new Map(); // frameIdx -> Map<uid, [pid, tid, x, y]>
      this.unitIconCache = new Map(); // typeId -> HTMLImageElement | null (failed)

      this.currentTime = 0;
      this.duration = 0;
      this.speed = 1;
      this.playing = false;
      this.showIcons = true;

      // View transform (pan & zoom)
      this.zoom = 1;
      this.panX = 0;
      this.panY = 0;

      this._rafId = null;
      this._lastTickMs = 0;
      this._lastRenderedUnits = [];

      this._bindInteractions();
      this._resizeObserver = new ResizeObserver(() => this.resize());
      this._resizeObserver.observe(this.canvas.parentElement || this.canvas);
      this.resize();
    }

    setData(replayData, minimapImg) {
      this.pause();
      this.data = replayData;
      this.minimapImg = minimapImg || null;
      this.duration = Math.max(1, replayData.meta?.duration_sec || 1);
      this.currentTime = 0;

      this.playersById.clear();
      for (const p of replayData.players || []) {
        this.playersById.set(p.pid, p);
      }

      this._buildKeyframeCache();
      this.resetView();
      this.render();
      this.onTimeUpdate(this.currentTime, this.duration, this._countUnitsAt(0));
    }

    _buildKeyframeCache() {
      this.keyframeStates.clear();
      const frames = this.data?.frames || [];
      let state = new Map();

      for (let i = 0; i < frames.length; i++) {
        const f = frames[i];
        if (f.is_keyframe || i === 0) {
          state = new Map();
          for (const u of f.units || []) {
            state.set(u[0], [u[1], u[2], u[3], u[4]]);
          }
          this.keyframeStates.set(i, new Map(state));
        } else {
          for (const uid of f.removed || []) {
            state.delete(uid);
          }
          for (const u of f.units || []) {
            state.set(u[0], [u[1], u[2], u[3], u[4]]);
          }
        }
      }
    }

    _getStateAtFrame(frameIdx) {
      const frames = this.data?.frames || [];
      if (!frames.length) return new Map();
      const clamped = Math.max(0, Math.min(frameIdx, frames.length - 1));

      // Find nearest cached keyframe <= clamped
      let startIdx = 0;
      for (let i = clamped; i >= 0; i--) {
        if (this.keyframeStates.has(i)) {
          startIdx = i;
          break;
        }
      }

      const state = new Map();
      const base = this.keyframeStates.get(startIdx);
      if (base) {
        for (const [uid, val] of base.entries()) {
          state.set(uid, val);
        }
      }

      for (let i = startIdx + 1; i <= clamped; i++) {
        const f = frames[i];
        for (const uid of f.removed || []) {
          state.delete(uid);
        }
        for (const u of f.units || []) {
          state.set(u[0], [u[1], u[2], u[3], u[4]]);
        }
      }
      return state;
    }

    _findFrameBracket(timeSec) {
      const frames = this.data?.frames || [];
      if (!frames.length) return { idx0: 0, idx1: 0, alpha: 0 };
      if (timeSec <= frames[0].time_sec) return { idx0: 0, idx1: 0, alpha: 0 };
      const last = frames.length - 1;
      if (timeSec >= frames[last].time_sec) return { idx0: last, idx1: last, alpha: 0 };

      let lo = 0;
      let hi = last;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (frames[mid].time_sec <= timeSec) lo = mid + 1;
        else hi = mid - 1;
      }
      const idx0 = Math.max(0, hi);
      const idx1 = Math.min(last, idx0 + 1);
      const t0 = frames[idx0].time_sec;
      const t1 = frames[idx1].time_sec;
      const alpha = t1 > t0 ? (timeSec - t0) / (t1 - t0) : 0;
      return { idx0, idx1, alpha: Math.max(0, Math.min(1, alpha)) };
    }

    _countUnitsAt(timeSec) {
      const { idx0 } = this._findFrameBracket(timeSec);
      return this._getStateAtFrame(idx0).size;
    }

    _getUnitIcon(typeId) {
      if (this.unitIconCache.has(typeId)) {
        return this.unitIconCache.get(typeId);
      }
      const name = this.data?.unit_dict?.[typeId];
      if (!name) {
        this.unitIconCache.set(typeId, null);
        return null;
      }
      const img = new Image();
      img.crossOrigin = "anonymous";
      img._loaded = false;
      img._failed = false;
      img.onload = () => {
        img._loaded = true;
        if (!this.playing) this.render();
      };
      img.onerror = () => {
        img._failed = true;
      };
      img.src = resolveUnitIconPath(name, this.iconsBase);
      this.unitIconCache.set(typeId, img);
      return img;
    }

    resize() {
      const parent = this.canvas.parentElement;
      if (!parent) return;
      const rect = parent.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      this.canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      this.dpr = dpr;
      this.viewW = rect.width;
      this.viewH = rect.height;
      this.render();
    }

    play() {
      if (this.playing || !this.data) return;
      if (this.currentTime >= this.duration) {
        this.currentTime = 0;
      }
      this.playing = true;
      this._lastTickMs = performance.now();
      this.onPlayStateChange(true);
      const tick = (now) => {
        if (!this.playing) return;
        const dt = Math.min(0.1, (now - this._lastTickMs) / 1000);
        this._lastTickMs = now;
        this.currentTime = Math.min(this.duration, this.currentTime + dt * this.speed);
        this.render();
        this.onTimeUpdate(this.currentTime, this.duration, this._lastRenderedUnits.length);
        if (this.currentTime >= this.duration) {
          this.pause();
          return;
        }
        this._rafId = requestAnimationFrame(tick);
      };
      this._rafId = requestAnimationFrame(tick);
    }

    pause() {
      if (!this.playing) return;
      this.playing = false;
      if (this._rafId) cancelAnimationFrame(this._rafId);
      this._rafId = null;
      this.onPlayStateChange(false);
    }

    togglePlay() {
      if (this.playing) this.pause();
      else this.play();
    }

    seek(timeSec) {
      this.currentTime = Math.max(0, Math.min(this.duration, Number(timeSec) || 0));
      this.render();
      this.onTimeUpdate(this.currentTime, this.duration, this._lastRenderedUnits.length);
    }

    setSpeed(mult) {
      this.speed = Number(mult) || 1;
    }

    setShowIcons(flag) {
      this.showIcons = Boolean(flag);
      this.render();
    }

    resetView() {
      this.zoom = 1;
      this.panX = 0;
      this.panY = 0;
      this.render();
    }

    zoomBy(factor, centerX, centerY) {
      const prevZoom = this.zoom;
      const nextZoom = Math.max(1, Math.min(8, prevZoom * factor));
      if (nextZoom === prevZoom) return;

      const cx = centerX !== undefined ? centerX : (this.viewW || 300) / 2;
      const cy = centerY !== undefined ? centerY : (this.viewH || 300) / 2;
      const scale = nextZoom / prevZoom;
      this.panX = cx - (cx - this.panX) * scale;
      this.panY = cy - (cy - this.panY) * scale;
      this.zoom = nextZoom;
      this._clampPan();
      this.render();
    }

    _clampPan() {
      const w = this.viewW || 300;
      const h = this.viewH || 300;
      const maxOffset = Math.max(w, h) * (this.zoom - 1) * 0.65 + 40;
      this.panX = Math.max(-maxOffset, Math.min(maxOffset, this.panX));
      this.panY = Math.max(-maxOffset, Math.min(maxOffset, this.panY));
    }

    _getMapRect() {
      const w = this.viewW || 300;
      const h = this.viewH || 300;
      const mw = this.data?.meta?.map_width || 200;
      const mh = this.data?.meta?.map_height || 200;
      const aspect = mw / mh;

      let drawW = w;
      let drawH = w / aspect;
      if (drawH > h) {
        drawH = h;
        drawW = h * aspect;
      }
      const ox = (w - drawW) / 2;
      const oy = (h - drawH) / 2;
      return { ox, oy, drawW, drawH, mw, mh };
    }

    render() {
      const ctx = this.ctx;
      if (!ctx) return;
      const w = this.viewW || 300;
      const h = this.viewH || 300;

      ctx.save();
      ctx.scale(this.dpr || 1, this.dpr || 1);
      ctx.fillStyle = "#06090f";
      ctx.fillRect(0, 0, w, h);

      if (!this.data) {
        ctx.restore();
        return;
      }

      ctx.translate(this.panX, this.panY);
      ctx.scale(this.zoom, this.zoom);

      const { ox, oy, drawW, drawH, mw, mh } = this._getMapRect();

      // Minimap background
      if (this.minimapImg && this.minimapImg.complete && this.minimapImg.naturalWidth > 0) {
        ctx.drawImage(this.minimapImg, ox, oy, drawW, drawH);
        ctx.fillStyle = "rgba(6, 9, 15, 0.25)";
        ctx.fillRect(ox, oy, drawW, drawH);
      } else {
        ctx.fillStyle = "#111827";
        ctx.fillRect(ox, oy, drawW, drawH);
        ctx.strokeStyle = "rgba(255,255,255,0.06)";
        ctx.lineWidth = 1 / this.zoom;
        const step = drawW / 8;
        for (let i = 1; i < 8; i++) {
          ctx.beginPath();
          ctx.moveTo(ox + i * step, oy);
          ctx.lineTo(ox + i * step, oy + drawH);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(ox, oy + i * step);
          ctx.lineTo(ox + drawW, oy + i * step);
          ctx.stroke();
        }
      }

      // Active battle pulses
      for (const b of this.data.battles || []) {
        if (this.currentTime >= b.start_sec - 3 && this.currentTime <= b.end_sec + 3) {
          const bx = ox + (b.x / mw) * drawW;
          const by = oy + (1 - b.y / mh) * drawH;
          const pulse = 0.5 + 0.5 * Math.sin(performance.now() / 160);
          const radius = (14 + pulse * 8) / Math.sqrt(this.zoom);
          ctx.beginPath();
          ctx.arc(bx, by, radius, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(239, 68, 68, 0.85)";
          ctx.lineWidth = 2 / this.zoom;
          ctx.stroke();
          ctx.fillStyle = "rgba(239, 68, 68, 0.16)";
          ctx.fill();
        }
      }

      // Interpolate units
      const { idx0, idx1, alpha } = this._findFrameBracket(this.currentTime);
      const state0 = this._getStateAtFrame(idx0);
      const state1 = idx1 !== idx0 ? this._getStateAtFrame(idx1) : state0;
      const unitDict = this.data.unit_dict || {};

      const rendered = [];
      const invScale = 1 / Math.sqrt(this.zoom);

      for (const [uid, u0] of state0.entries()) {
        const pid = u0[0];
        const typeId = u0[1];
        let ux = u0[2];
        let uy = u0[3];

        const u1 = state1.get(uid);
        if (u1 && alpha > 0) {
          ux = ux + (u1[2] - ux) * alpha;
          uy = uy + (u1[3] - uy) * alpha;
        }

        const cx = ox + (ux / mw) * drawW;
        const cy = oy + (1 - uy / mh) * drawH;
        const unitName = unitDict[typeId] || "Unit";
        const player = this.playersById.get(pid);
        const color = player?.color_hex || "#ffffff";
        const isBuilding = BUILDING_NAMES.has(unitName);
        const isWorker = WORKER_NAMES.has(unitName);

        rendered.push({ uid, pid, unitName, playerName: player?.name || `P${pid}`, cx, cy });

        const icon = this.showIcons ? this._getUnitIcon(typeId) : null;
        const canDrawIcon = icon && icon._loaded && !icon._failed && (this.zoom >= 1.5 || isBuilding);

        if (canDrawIcon) {
          const size = (isBuilding ? 11 : 9) * invScale;
          ctx.fillStyle = color;
          ctx.fillRect(cx - size / 2 - 1 * invScale, cy - size / 2 - 1 * invScale, size + 2 * invScale, size + 2 * invScale);
          ctx.drawImage(icon, cx - size / 2, cy - size / 2, size, size);
        } else if (isBuilding) {
          const size = 6.5 * invScale;
          ctx.fillStyle = color;
          ctx.fillRect(cx - size / 2, cy - size / 2, size, size);
          ctx.strokeStyle = "rgba(0,0,0,0.7)";
          ctx.lineWidth = 1 * invScale;
          ctx.strokeRect(cx - size / 2, cy - size / 2, size, size);
        } else {
          const r = (isWorker ? 2.2 : 3.2) * invScale;
          ctx.beginPath();
          ctx.arc(cx, cy, r, 0, Math.PI * 2);
          ctx.fillStyle = color;
          ctx.fill();
          ctx.strokeStyle = "rgba(0,0,0,0.65)";
          ctx.lineWidth = 0.8 * invScale;
          ctx.stroke();
        }
      }

      this._lastRenderedUnits = rendered;
      ctx.restore();
    }

    _bindInteractions() {
      let dragging = false;
      let moved = false;
      let startX = 0;
      let startY = 0;
      let pinchDist = 0;

      const getLocalXY = (clientX, clientY) => {
        const rect = this.canvas.getBoundingClientRect();
        return { x: clientX - rect.left, y: clientY - rect.top };
      };

      this.canvas.addEventListener("wheel", (e) => {
        e.preventDefault();
        const pos = getLocalXY(e.clientX, e.clientY);
        const factor = e.deltaY < 0 ? 1.18 : 1 / 1.18;
        this.zoomBy(factor, pos.x, pos.y);
      }, { passive: false });

      this.canvas.addEventListener("mousedown", (e) => {
        dragging = true;
        moved = false;
        startX = e.clientX;
        startY = e.clientY;
      });

      window.addEventListener("mousemove", (e) => {
        if (!dragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) moved = true;
        startX = e.clientX;
        startY = e.clientY;
        this.panX += dx;
        this.panY += dy;
        this._clampPan();
        this.render();
      });

      window.addEventListener("mouseup", (e) => {
        if (!dragging) return;
        dragging = false;
        if (!moved) {
          const pos = getLocalXY(e.clientX, e.clientY);
          this._hitTest(pos.x, pos.y);
        }
      });

      this.canvas.addEventListener("touchstart", (e) => {
        if (e.touches.length === 1) {
          dragging = true;
          moved = false;
          startX = e.touches[0].clientX;
          startY = e.touches[0].clientY;
        } else if (e.touches.length === 2) {
          dragging = false;
          pinchDist = Math.hypot(
            e.touches[0].clientX - e.touches[1].clientX,
            e.touches[0].clientY - e.touches[1].clientY
          );
        }
      }, { passive: true });

      this.canvas.addEventListener("touchmove", (e) => {
        e.preventDefault();
        if (e.touches.length === 1 && dragging) {
          const dx = e.touches[0].clientX - startX;
          const dy = e.touches[0].clientY - startY;
          if (Math.abs(dx) > 3 || Math.abs(dy) > 3) moved = true;
          startX = e.touches[0].clientX;
          startY = e.touches[0].clientY;
          this.panX += dx;
          this.panY += dy;
          this._clampPan();
          this.render();
        } else if (e.touches.length === 2) {
          const dist = Math.hypot(
            e.touches[0].clientX - e.touches[1].clientX,
            e.touches[0].clientY - e.touches[1].clientY
          );
          if (pinchDist > 0) {
            const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
            const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
            const pos = getLocalXY(midX, midY);
            this.zoomBy(dist / pinchDist, pos.x, pos.y);
          }
          pinchDist = dist;
        }
      }, { passive: false });

      this.canvas.addEventListener("touchend", (e) => {
        if (dragging && !moved && e.changedTouches.length === 1) {
          const pos = getLocalXY(e.changedTouches[0].clientX, e.changedTouches[0].clientY);
          this._hitTest(pos.x, pos.y);
        }
        if (e.touches.length < 2) pinchDist = 0;
        if (e.touches.length === 0) dragging = false;
      });
    }

    _hitTest(viewX, viewY) {
      const worldX = (viewX - this.panX) / this.zoom;
      const worldY = (viewY - this.panY) / this.zoom;
      const threshold = 10 / Math.sqrt(this.zoom);

      let best = null;
      let bestDist = threshold;
      for (const u of this._lastRenderedUnits) {
        const d = Math.hypot(u.cx - worldX, u.cy - worldY);
        if (d < bestDist) {
          bestDist = d;
          best = u;
        }
      }
      this.onUnitSelect(best);
    }
  }

  global.ReplayPlayer = ReplayPlayer;
  global.resolveUnitIconPath = resolveUnitIconPath;
})(window);
