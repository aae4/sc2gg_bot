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
    overseercocoon: "overseer",
    lurkeregg: "lurker",
    lurkermpegg: "lurker",
    transportoverlordcocoon: "overlord",
    templararchive: "templararchives",
    assimilatorrich: "assimilator",
    refineryrich: "refinery",
    extractorrich: "extractor",
  };

  const BUILDING_NAMES = new Set([
    "CommandCenter", "CommandCenterFlying", "OrbitalCommand", "OrbitalCommandFlying",
    "PlanetaryFortress", "SupplyDepot", "SupplyDepotLowered",
    "Refinery", "RefineryRich", "Barracks", "BarracksFlying", "EngineeringBay", "Bunker",
    "MissileTurret", "SensorTower", "Factory", "FactoryFlying", "GhostAcademy", "Armory",
    "Starport", "StarportFlying", "FusionCore", "TechLab", "Reactor",
    "BarracksReactor", "BarracksTechLab", "FactoryReactor", "FactoryTechLab", "StarportReactor", "StarportTechLab",
    "Nexus", "Pylon", "Assimilator", "AssimilatorRich", "Gateway", "WarpGate", "Forge", "CyberneticsCore",
    "PhotonCannon", "ShieldBattery", "RoboticsFacility", "RoboticsBay", "Stargate", "FleetBeacon",
    "TwilightCouncil", "TemplarArchive", "TemplarArchives", "DarkShrine",
    "Hatchery", "Lair", "Hive", "Extractor", "ExtractorRich", "SpawningPool", "EvolutionChamber",
    "RoachWarren", "BanelingNest", "SpineCrawler", "SpineCrawlerUprooted", "SporeCrawler", "SporeCrawlerUprooted",
    "HydraliskDen", "LurkerDen", "LurkerDenMP", "InfestationPit", "Spire", "GreaterSpire",
    "NydusNetwork", "NydusWorm", "NydusCanal", "UltraliskCavern",
    "CreepTumor", "CreepTumorBurrowed", "CreepTumorQueen",
  ]);

  const WORKER_NAMES = new Set(["SCV", "Probe", "Drone"]);

  // Non-army / supply / utility / summon units excluded from army counts & army layer
  const NON_ARMY_UNIT_NAMES = new Set([
    "Overlord", "OverlordTransport", "OverlordCocoon", "TransportOverlordCocoon",
    "Overseer", "OverseerSiegeMode", "OverseerCocoon",
    "Larva", "Egg", "MULE",
    "Changeling", "ChangelingMarine", "ChangelingMarineShield",
    "ChangelingZealot", "ChangelingZergling", "ChangelingZerglingWings",
    "Broodling", "BroodlingEscort", "Interceptor", "LocustMP", "LocustMPFlying",
    "AutoTurret", "PointDefenseDrone", "KD8Charge", "AdeptPhaseShift", "DisruptorPhased",
  ]);

  const UNIT_RANGES = {
    marine: { attack: 5, sight: 9 },
    marauder: { attack: 6, sight: 10 },
    reaper: { attack: 5, sight: 9 },
    ghost: { attack: 6, sight: 11 },
    hellion: { attack: 5, sight: 10 },
    helliontank: { attack: 2, sight: 10 },
    siegetank: { attack: 7, sight: 11 },
    siegetanksieged: { attack: 13, sight: 11 },
    cyclone: { attack: 7, sight: 11 },
    thor: { attack: 10, sight: 11 },
    vikingfighter: { attack: 9, sight: 10 },
    vikingassault: { attack: 6, sight: 10 },
    liberator: { attack: 5, sight: 10 },
    liberatorag: { attack: 10, sight: 10 },
    banshee: { attack: 6, sight: 10 },
    raven: { attack: 0, sight: 11 },
    battlecruiser: { attack: 6, sight: 12 },
    missileturret: { attack: 7, sight: 11 },
    sensortower: { attack: 0, sight: 30 },
    bunker: { attack: 6, sight: 10 },
    planetaryfortress: { attack: 6, sight: 11 },
    zealot: { attack: 0.1, sight: 9 },
    stalker: { attack: 6, sight: 10 },
    sentry: { attack: 5, sight: 10 },
    adept: { attack: 4, sight: 9 },
    immortal: { attack: 6, sight: 9 },
    colossus: { attack: 7, sight: 10 },
    disruptor: { attack: 0, sight: 9 },
    hightemplar: { attack: 6, sight: 10 },
    phoenix: { attack: 5, sight: 10 },
    voidray: { attack: 6, sight: 10 },
    oracle: { attack: 4, sight: 10 },
    tempest: { attack: 14, sight: 12 },
    carrier: { attack: 8, sight: 12 },
    photoncannon: { attack: 7, sight: 11 },
    observer: { attack: 0, sight: 11 },
    observersiegemode: { attack: 0, sight: 13.75 },
    zergling: { attack: 0.1, sight: 8 },
    baneling: { attack: 0.25, sight: 8 },
    roach: { attack: 4, sight: 9 },
    ravager: { attack: 6, sight: 9 },
    hydralisk: { attack: 5, sight: 9 },
    lurkermp: { attack: 0, sight: 10 },
    lurkermpburrowed: { attack: 10, sight: 10 },
    mutalisk: { attack: 3, sight: 11 },
    corruptor: { attack: 6, sight: 10 },
    viper: { attack: 0, sight: 11 },
    broodlord: { attack: 10, sight: 12 },
    ultralisk: { attack: 1, sight: 8 },
    queen: { attack: 5, sight: 9 },
    spinecrawler: { attack: 7, sight: 11 },
    sporecrawler: { attack: 7, sight: 11 },
    overlord: { attack: 0, sight: 11 },
    overseer: { attack: 0, sight: 11 },
  };

  function getUnitRanges(unitName) {
    const slug = String(unitName || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    return UNIT_RANGES[slug] || { attack: 0, sight: 9 };
  }

  const ABILITY_STYLES = {
    PsiStorm: { kind: "aoe", label: "Storm", color: "#38bdf8", fill: "rgba(56, 189, 248, 0.22)", radius: 1.8, duration: 2.8 },
    EMP: { kind: "aoe", label: "EMP", color: "#60a5fa", fill: "rgba(96, 165, 250, 0.24)", radius: 1.8, duration: 1.6 },
    FungalGrowth: { kind: "aoe", label: "Fungal", color: "#4ade80", fill: "rgba(74, 222, 128, 0.22)", radius: 2.25, duration: 2.4 },
    CorrosiveBile: { kind: "aoe", label: "Bile", color: "#a3e635", fill: "rgba(163, 230, 53, 0.24)", radius: 1.1, duration: 1.8 },
    BlindingCloud: { kind: "aoe", label: "Cloud", color: "#84cc16", fill: "rgba(132, 204, 22, 0.22)", radius: 2.2, duration: 3.0 },
    ScannerSweep: { kind: "aoe", label: "Scan", color: "#93c5fd", fill: "rgba(147, 197, 253, 0.12)", radius: 7.5, duration: 2.8, dashed: true },
    ForceField: { kind: "aoe", label: "FF", color: "#22d3ee", fill: "rgba(34, 211, 238, 0.20)", radius: 1.5, duration: 2.6 },
    GuardianShield: { kind: "aoe", label: "Shield", color: "#67e8f9", fill: "rgba(103, 232, 249, 0.14)", radius: 4.5, duration: 2.8, dashed: true },
    PurificationNova: { kind: "aoe", label: "Nova", color: "#fb923c", fill: "rgba(251, 146, 60, 0.26)", radius: 1.6, duration: 1.8 },
    AntiArmorMissile: { kind: "aoe", label: "AAM", color: "#f97316", fill: "rgba(249, 115, 22, 0.22)", radius: 2.5, duration: 2.0 },
    ParasiticBomb: { kind: "aoe", label: "PBomb", color: "#a855f7", fill: "rgba(168, 85, 247, 0.22)", radius: 2.5, duration: 2.4 },
    Blink: { kind: "bolt", label: "Blink", color: "#38bdf8", duration: 1.2 },
    YamatoGun: { kind: "bolt", label: "Yamato", color: "#f97316", duration: 1.5 },
    Yamato: { kind: "bolt", label: "Yamato", color: "#f97316", duration: 1.5 },
    Snipe: { kind: "bolt", label: "Snipe", color: "#ef4444", duration: 1.4 },
    Feedback: { kind: "bolt", label: "Feedback", color: "#c084fc", duration: 1.3 },
    Transfuse: { kind: "bolt", label: "Transfuse", color: "#4ade80", duration: 1.3 },
    Abduct: { kind: "bolt", label: "Abduct", color: "#c084fc", duration: 1.4 },
    InterferenceMatrix: { kind: "bolt", label: "Matrix", color: "#facc15", duration: 1.4 },
    InjectLarva: { kind: "bolt", label: "Inject", color: "#a855f7", duration: 1.2, subtle: true },
    ChronoBoost: { kind: "bolt", label: "Chrono", color: "#38bdf8", duration: 1.2, subtle: true },
  };

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
      this.hdMapImg = null;
      this.mapMode = "hd"; // "hd" | "tactical"
      this.playersById = new Map();
      this.keyframeStates = new Map(); // frameIdx -> Map<uid, [pid, tid, x, y]>
      this.deaths = [];
      this.deathsByUid = new Map();
      this.abilityCasts = [];
      this.unitIconCache = new Map(); // typeId -> HTMLImageElement | null (failed)

      this.currentTime = 0;
      this.duration = 0;
      this.speed = 1;
      this.playing = false;
      this.showIcons = true;
      this.layerFilter = "all"; // "all" | "army" | "workers" | "buildings"

      this.selectedUnitUid = null;
      this.inspectedArea = null; // { ux, uy, radius }
      this._lastStatsByPid = {};

      // View transform (pan & zoom)
      this.zoom = 1;
      this.panX = 0;
      this.panY = 0;

      this._rafId = null;
      this._cameraAnimRaf = null;
      this._lastTickMs = 0;
      this._lastRenderedUnits = [];
      this._lastTouchEndMs = 0;
      this._abortController = new AbortController();

      this._bindInteractions();
      this._resizeObserver = new ResizeObserver(() => this.resize());
      this._resizeObserver.observe(this.canvas.parentElement || this.canvas);
      this.resize();
    }

    destroy() {
      this.pause();
      this._cancelCameraAnim();
      this._abortController.abort();
      if (this._resizeObserver) {
        this._resizeObserver.disconnect();
      }
    }

    setData(replayData, minimapImg, hdMapImg) {
      this.pause();
      this.data = replayData;
      this.minimapImg = minimapImg || null;
      this.hdMapImg = hdMapImg || null;
      this.mapMode = this.hasHdMap() ? "hd" : "tactical";
      this.duration = Math.max(1, replayData.meta?.duration_sec || 1);
      this.currentTime = 0;
      this.selectedUnitUid = null;
      this.inspectedArea = null;
      this.onUnitSelect(null);

      this.playersById.clear();
      for (const p of replayData.players || []) {
        this.playersById.set(p.pid, p);
      }

      this._buildKeyframeCache();
      this._buildDeathIndex(replayData.deaths || []);
      this._buildAbilityIndex(replayData.ability_casts || []);
      this.resetView();
      this.render();
      this.onTimeUpdate(
        this.currentTime,
        this.duration,
        this._lastRenderedUnits.length,
        this._lastStatsByPid
      );
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

    _buildDeathIndex(rawDeaths) {
      const parsed = [];
      this.deathsByUid.clear();
      for (const d of rawDeaths) {
        if (!Array.isArray(d) || d.length < 6) continue;
        const item = {
          timeSec: Number(d[0]) || 0,
          uid: d[1],
          pid: d[2],
          typeId: d[3],
          x: Number(d[4]) || 0,
          y: Number(d[5]) || 0,
          killerUid: d[6] ?? null,
          killerPid: d[7] ?? null,
          killerTypeId: d[8] ?? null,
          value: Number(d[9]) || 0,
          hasExplicitKillerPos: d.length >= 12,
          killerX: d[10] !== null && d[10] !== undefined ? Number(d[10]) : null,
          killerY: d[11] !== null && d[11] !== undefined ? Number(d[11]) : null,
        };
        parsed.push(item);
        if (item.uid !== null && item.uid !== undefined) {
          this.deathsByUid.set(item.uid, item);
        }
      }
      parsed.sort((a, b) => a.timeSec - b.timeSec);
      this.deaths = parsed;
    }

    _findInTimeWindow(list, fromSec, toSec) {
      if (!list.length || toSec < fromSec) return [];
      let lo = 0;
      let hi = list.length - 1;
      let start = list.length;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (list[mid].timeSec >= fromSec) {
          start = mid;
          hi = mid - 1;
        } else {
          lo = mid + 1;
        }
      }
      const res = [];
      for (let i = start; i < list.length; i++) {
        if (list[i].timeSec > toSec) break;
        res.push(list[i]);
      }
      return res;
    }

    _findDeathsInWindow(fromSec, toSec) {
      return this._findInTimeWindow(this.deaths, fromSec, toSec);
    }

    _buildAbilityIndex(rawCasts) {
      const parsed = [];
      for (const c of rawCasts) {
        if (!Array.isArray(c) || c.length < 3) continue;
        parsed.push({
          timeSec: Number(c[0]) || 0,
          pid: c[1],
          abilityId: c[2],
          x: c[3] !== null && c[3] !== undefined ? Number(c[3]) : null,
          y: c[4] !== null && c[4] !== undefined ? Number(c[4]) : null,
        });
      }
      parsed.sort((a, b) => a.timeSec - b.timeSec);
      this.abilityCasts = parsed;
    }

    _findAbilitiesInWindow(fromSec, toSec) {
      return this._findInTimeWindow(this.abilityCasts, fromSec, toSec);
    }

    _getLayerAlpha(unitName) {
      const isBuilding = BUILDING_NAMES.has(unitName);
      const isWorker = WORKER_NAMES.has(unitName);
      const isNonArmy = NON_ARMY_UNIT_NAMES.has(unitName);
      if (this.layerFilter === "army") {
        if (isWorker || isNonArmy) return 0;
        if (isBuilding) return 0.16;
      } else if (this.layerFilter === "workers") {
        if (!isWorker && !isBuilding) return 0;
        if (isBuilding) return 0.16;
      } else if (this.layerFilter === "buildings") {
        if (!isBuilding) return 0;
      }
      return 1;
    }

    _resolveUnitPos(uid, state0, state1, alpha, t0) {
      const u0 = state0.get(uid);
      if (u0) {
        let ux = u0[2];
        let uy = u0[3];
        const u1 = state1.get(uid);
        const death = this.deathsByUid.get(uid);
        if (u1 && alpha > 0) {
          ux = ux + (u1[2] - ux) * alpha;
          uy = uy + (u1[3] - uy) * alpha;
        } else if (death && !u1 && death.timeSec > t0) {
          const dAlpha = Math.max(0, Math.min(1, (this.currentTime - t0) / (death.timeSec - t0)));
          ux = ux + (death.x - ux) * dAlpha;
          uy = uy + (death.y - uy) * dAlpha;
        }
        return { x: ux, y: uy };
      }
      const death = this.deathsByUid.get(uid);
      if (death && Math.abs(this.currentTime - death.timeSec) <= 3) {
        return { x: death.x, y: death.y };
      }
      return null;
    }

    _findFrameBracket(timeSec) {
      const frames = this.data?.frames || [];
      if (!frames.length) return { idx0: 0, idx1: 0, alpha: 0, t0: 0, t1: 0 };
      if (timeSec <= frames[0].time_sec) {
        return { idx0: 0, idx1: 0, alpha: 0, t0: frames[0].time_sec, t1: frames[0].time_sec };
      }
      const last = frames.length - 1;
      if (timeSec >= frames[last].time_sec) {
        return { idx0: last, idx1: last, alpha: 0, t0: frames[last].time_sec, t1: frames[last].time_sec };
      }

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
      return { idx0, idx1, alpha: Math.max(0, Math.min(1, alpha)), t0, t1 };
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
        this.onTimeUpdate(
          this.currentTime,
          this.duration,
          this._lastRenderedUnits.length,
          this._lastStatsByPid
        );
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
      this.onTimeUpdate(
        this.currentTime,
        this.duration,
        this._lastRenderedUnits.length,
        this._lastStatsByPid
      );
    }

    setSpeed(mult) {
      this.speed = Number(mult) || 1;
    }

    setShowIcons(flag) {
      this.showIcons = Boolean(flag);
      this.render();
    }

    setLayerFilter(mode) {
      this.layerFilter = mode || "all";
      this.clearSelection();
    }

    clearSelection() {
      this.selectedUnitUid = null;
      this.inspectedArea = null;
      this.render();
      this.onUnitSelect(null);
    }

    _cancelCameraAnim() {
      if (this._cameraAnimRaf !== null) {
        cancelAnimationFrame(this._cameraAnimRaf);
        this._cameraAnimRaf = null;
      }
    }

    focusOn(gx, gy, targetZoom = 3.0, durationMs = 420) {
      if (!Number.isFinite(gx) || !Number.isFinite(gy)) return;
      this._cancelCameraAnim();

      const w = this.viewW || 300;
      const h = this.viewH || 300;
      const { ox, oy, drawW, drawH, minX, minY, spanX, spanY } = this._getMapRect();
      const wx = ox + ((gx - minX) / spanX) * drawW;
      const wy = oy + (1 - (gy - minY) / spanY) * drawH;

      const toZoom = Math.max(1, Math.min(8, targetZoom));
      const maxOffset = Math.max(w, h) * (toZoom - 1) * 0.65 + 40;
      const toPanX = Math.max(-maxOffset, Math.min(maxOffset, w / 2 - wx * toZoom));
      const toPanY = Math.max(-maxOffset, Math.min(maxOffset, h / 2 - wy * toZoom));

      if (durationMs <= 0) {
        this.zoom = toZoom;
        this.panX = toPanX;
        this.panY = toPanY;
        this._clampPan();
        this.render();
        return;
      }

      const fromZoom = this.zoom;
      const fromPanX = this.panX;
      const fromPanY = this.panY;
      const startMs = performance.now();

      const step = (now) => {
        const raw = Math.min(1, (now - startMs) / durationMs);
        const eased = 1 - Math.pow(1 - raw, 3);
        this.zoom = fromZoom + (toZoom - fromZoom) * eased;
        this.panX = fromPanX + (toPanX - fromPanX) * eased;
        this.panY = fromPanY + (toPanY - fromPanY) * eased;
        this._clampPan();
        if (!this.playing) this.render();

        if (raw < 1) {
          this._cameraAnimRaf = requestAnimationFrame(step);
        } else {
          this._cameraAnimRaf = null;
        }
      };

      this._cameraAnimRaf = requestAnimationFrame(step);
    }

    resetView() {
      this._cancelCameraAnim();
      this.zoom = 1;
      this.panX = 0;
      this.panY = 0;
      this.render();
    }

    zoomBy(factor, centerX, centerY) {
      this._cancelCameraAnim();
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
      const { ox, oy, drawW, drawH } = this._getMapRect();
      const pad = 40;

      const clampAxis = (pan, start, size, viewSize) => {
        const minScreen = start * this.zoom;
        const maxScreen = (start + size) * this.zoom;
        if (maxScreen - minScreen <= viewSize) {
          const centerPan = (viewSize - (minScreen + maxScreen)) / 2;
          return Math.max(centerPan - pad, Math.min(centerPan + pad, pan));
        }
        const minPan = viewSize - maxScreen - pad;
        const maxPan = pad - minScreen;
        return Math.max(minPan, Math.min(maxPan, pan));
      };

      this.panX = clampAxis(this.panX, ox, drawW, w);
      this.panY = clampAxis(this.panY, oy, drawH, h);
    }

    hasHdMap() {
      return Boolean(this.hdMapImg && this.hdMapImg.complete && this.hdMapImg.naturalWidth > 0);
    }

    setMapMode(mode) {
      if (mode === "hd" && this.hasHdMap()) {
        this.mapMode = "hd";
      } else {
        this.mapMode = "tactical";
      }
      this.render();
      return this.mapMode;
    }

    toggleMapMode() {
      return this.setMapMode(this.mapMode === "hd" ? "tactical" : "hd");
    }

    _getMapRect() {
      const w = this.viewW || 300;
      const h = this.viewH || 300;
      const mw = this.data?.meta?.map_width || 200;
      const mh = this.data?.meta?.map_height || 200;
      const bounds = this.data?.meta?.map_bounds;
      const hasBounds = Array.isArray(bounds) && bounds.length === 4 && bounds[2] > bounds[0] && bounds[3] > bounds[1];
      const minX = hasBounds ? bounds[0] : 0;
      const minY = hasBounds ? bounds[1] : 0;
      const spanX = hasBounds ? bounds[2] - bounds[0] : mw;
      const spanY = hasBounds ? bounds[3] - bounds[1] : mh;
      const aspect = spanX / spanY;

      let drawW = w;
      let drawH = w / aspect;
      if (drawH > h) {
        drawH = h;
        drawW = h * aspect;
      }
      const ox = (w - drawW) / 2;
      const oy = (h - drawH) / 2;
      return { ox, oy, drawW, drawH, minX, minY, spanX, spanY };
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

      const { ox, oy, drawW, drawH, minX, minY, spanX, spanY } = this._getMapRect();

      // Map background (HD render or tactical .s2ma map)
      const activeBg =
        this.mapMode === "hd" && this.hasHdMap()
          ? this.hdMapImg
          : this.minimapImg && this.minimapImg.complete && this.minimapImg.naturalWidth > 0
            ? this.minimapImg
            : this.hasHdMap()
              ? this.hdMapImg
              : null;

      if (activeBg) {
        ctx.drawImage(activeBg, ox, oy, drawW, drawH);
        ctx.fillStyle = this.mapMode === "hd" ? "rgba(6, 9, 15, 0.25)" : "rgba(6, 9, 15, 0.12)";
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
          const bx = ox + ((b.x - minX) / spanX) * drawW;
          const by = oy + (1 - (b.y - minY) / spanY) * drawH;
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
      const { idx0, idx1, alpha, t0 } = this._findFrameBracket(this.currentTime);
      const state0 = this._getStateAtFrame(idx0);
      const state1 = idx1 !== idx0 ? this._getStateAtFrame(idx1) : state0;
      const unitDict = this.data.unit_dict || {};

      const rendered = [];
      const statsByPid = {};
      const invScale = 1 / Math.sqrt(this.zoom);
      let selectedUnit = null;

      for (const [uid, u0] of state0.entries()) {
        const death = this.deathsByUid.get(uid);
        if (death && this.currentTime >= death.timeSec) {
          continue;
        }

        const pid = u0[0];
        const typeId = u0[1];
        let ux = u0[2];
        let uy = u0[3];

        const u1 = state1.get(uid);
        if (u1 && alpha > 0) {
          ux = ux + (u1[2] - ux) * alpha;
          uy = uy + (u1[3] - uy) * alpha;
        } else if (death && !u1 && death.timeSec > t0) {
          const dAlpha = Math.max(0, Math.min(1, (this.currentTime - t0) / (death.timeSec - t0)));
          ux = ux + (death.x - ux) * dAlpha;
          uy = uy + (death.y - uy) * dAlpha;
        }

        const unitName = unitDict[typeId] || "Unit";
        const isBuilding = BUILDING_NAMES.has(unitName);
        const isWorker = WORKER_NAMES.has(unitName);
        const isNonArmy = NON_ARMY_UNIT_NAMES.has(unitName);

        if (!statsByPid[pid]) {
          statsByPid[pid] = { workers: 0, army: 0, buildings: 0 };
        }
        if (isBuilding) statsByPid[pid].buildings += 1;
        else if (isWorker) statsByPid[pid].workers += 1;
        else if (!isNonArmy) statsByPid[pid].army += 1;

        const unitAlpha = this._getLayerAlpha(unitName);
        if (unitAlpha === 0) continue;

        const cx = ox + ((ux - minX) / spanX) * drawW;
        const cy = oy + (1 - (uy - minY) / spanY) * drawH;
        const player = this.playersById.get(pid);
        const color = player?.color_hex || "#ffffff";

        const entry = {
          uid,
          pid,
          unitName,
          playerName: player?.name || `P${pid}`,
          color,
          ux,
          uy,
          cx,
          cy,
          isBuilding,
          isWorker,
        };

        if (unitAlpha === 1) {
          rendered.push(entry);
        }
        if (this.selectedUnitUid === uid) {
          selectedUnit = entry;
        }

        ctx.globalAlpha = unitAlpha;
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

      ctx.globalAlpha = 1;

      const abilityDict = this.data.ability_dict || {};
      this._renderAbilityEffects(ctx, { ox, oy, drawW, drawH, minX, minY, spanX, spanY }, invScale, abilityDict);
      this._renderDeathEffects(ctx, { ox, oy, drawW, drawH, minX, minY, spanX, spanY }, state0, state1, alpha, t0, invScale, unitDict);

      // Unit or area inspector overlay
      if (selectedUnit) {
        const ranges = getUnitRanges(selectedUnit.unitName);
        if (ranges.sight > 0) {
          const sightPx = (ranges.sight / spanX) * drawW;
          ctx.save();
          ctx.beginPath();
          ctx.setLineDash([4 / this.zoom, 3 / this.zoom]);
          ctx.arc(selectedUnit.cx, selectedUnit.cy, sightPx, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(148, 163, 184, 0.45)";
          ctx.lineWidth = 1.2 / this.zoom;
          ctx.stroke();
          ctx.restore();
        }
        if (ranges.attack > 0.5) {
          const atkPx = (ranges.attack / spanX) * drawW;
          ctx.beginPath();
          ctx.arc(selectedUnit.cx, selectedUnit.cy, atkPx, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(245, 158, 11, 0.08)";
          ctx.fill();
          ctx.strokeStyle = "rgba(245, 158, 11, 0.75)";
          ctx.lineWidth = 1.4 / this.zoom;
          ctx.stroke();
        }
        ctx.beginPath();
        ctx.arc(selectedUnit.cx, selectedUnit.cy, 8 * invScale, 0, Math.PI * 2);
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.8 / this.zoom;
        ctx.stroke();
      } else if (this.inspectedArea) {
        const ax = ox + ((this.inspectedArea.ux - minX) / spanX) * drawW;
        const ay = oy + (1 - (this.inspectedArea.uy - minY) / spanY) * drawH;
        const ar = (this.inspectedArea.radius / spanX) * drawW;
        ctx.save();
        ctx.beginPath();
        ctx.setLineDash([5 / this.zoom, 4 / this.zoom]);
        ctx.arc(ax, ay, ar, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(59, 130, 246, 0.08)";
        ctx.fill();
        ctx.strokeStyle = "rgba(59, 130, 246, 0.75)";
        ctx.lineWidth = 1.5 / this.zoom;
        ctx.stroke();
        ctx.restore();
      }

      this._lastStatsByPid = statsByPid;
      this._lastRenderedUnits = rendered;
      ctx.restore();

      if (this.selectedUnitUid !== null && !selectedUnit) {
        this.selectedUnitUid = null;
        this.onUnitSelect(null);
      }
    }

    _renderAbilityEffects(ctx, rect, invScale, abilityDict) {
      const { ox, oy, drawW, drawH, minX, minY, spanX, spanY } = rect;
      const maxLifetime = 3.0;
      const recentCasts = this._findAbilitiesInWindow(this.currentTime - maxLifetime, this.currentTime);
      if (!recentCasts.length) return;

      const toCanvasX = (gx) => ox + ((gx - minX) / spanX) * drawW;
      const toCanvasY = (gy) => oy + (1 - (gy - minY) / spanY) * drawH;

      ctx.save();
      for (const c of recentCasts) {
        if (c.x === null || c.y === null) continue;
        const abilityName = abilityDict[c.abilityId] || "";
        const style = ABILITY_STYLES[abilityName] || {
          kind: "bolt",
          label: abilityName || "Cast",
          color: this.playersById.get(c.pid)?.color_hex || "#38bdf8",
          duration: 1.4,
        };

        const duration = style.duration || 1.8;
        const age = this.currentTime - c.timeSec;
        if (age < 0 || age > duration) continue;

        const progress = age / duration;
        const fade = 1 - progress;
        const ax = toCanvasX(c.x);
        const ay = toCanvasY(c.y);

        if (style.kind === "aoe") {
          const baseRadiusPx = Math.max((style.radius / spanX) * drawW, 6 * invScale);
          const spawnScale = progress < 0.15 ? 0.55 + (progress / 0.15) * 0.45 : 1.0;
          const rPx = baseRadiusPx * spawnScale;

          ctx.save();
          ctx.beginPath();
          ctx.arc(ax, ay, rPx, 0, Math.PI * 2);
          ctx.fillStyle = style.fill;
          ctx.globalAlpha = 0.85 * fade;
          ctx.fill();

          if (style.dashed) {
            ctx.setLineDash([4 * invScale, 3 * invScale]);
          }
          ctx.strokeStyle = style.color;
          ctx.globalAlpha = 0.92 * fade;
          ctx.lineWidth = 1.6 * invScale;
          ctx.stroke();
          ctx.restore();

          // Initial shockwave pulse inside AoE zone (0..0.55s)
          if (age <= 0.55) {
            const p = age / 0.55;
            ctx.beginPath();
            ctx.arc(ax, ay, rPx * (0.35 + p * 0.65), 0, Math.PI * 2);
            ctx.strokeStyle = style.color;
            ctx.globalAlpha = 0.7 * (1 - p);
            ctx.lineWidth = 1.1 * invScale;
            ctx.stroke();
          }

          if (this.zoom >= 1.8 && style.label) {
            ctx.font = `600 ${Math.round(8.5 * invScale)}px Inter, system-ui, sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.globalAlpha = 0.92 * fade;
            ctx.lineWidth = 2.4 * invScale;
            ctx.strokeStyle = "rgba(6, 9, 15, 0.9)";
            ctx.strokeText(style.label, ax, ay - rPx - 5 * invScale);
            ctx.fillStyle = style.color;
            ctx.fillText(style.label, ax, ay - rPx - 5 * invScale);
          }
        } else {
          const alphaMul = style.subtle ? 0.55 : 1.0;
          const flashR = (style.subtle ? 2.5 + progress * 6.5 : 3.5 + progress * 10.0) * invScale;

          ctx.beginPath();
          ctx.arc(ax, ay, flashR, 0, Math.PI * 2);
          ctx.strokeStyle = style.color;
          ctx.globalAlpha = 0.85 * fade * alphaMul;
          ctx.lineWidth = (style.subtle ? 1.2 : 1.8) * invScale;
          ctx.stroke();

          const boltSize = Math.round((style.subtle ? 9 : 12) * invScale);
          ctx.font = `700 ${boltSize}px Inter, system-ui, sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.globalAlpha = 0.95 * fade * alphaMul;
          ctx.lineWidth = 2.4 * invScale;
          ctx.strokeStyle = "rgba(6, 9, 15, 0.9)";
          ctx.strokeText("⚡", ax, ay);
          ctx.fillStyle = style.color;
          ctx.fillText("⚡", ax, ay);

          if (this.zoom >= 1.8 && style.label && !style.subtle) {
            ctx.font = `600 ${Math.round(8.5 * invScale)}px Inter, system-ui, sans-serif`;
            ctx.globalAlpha = 0.9 * fade;
            ctx.lineWidth = 2.4 * invScale;
            ctx.strokeStyle = "rgba(6, 9, 15, 0.9)";
            ctx.strokeText(style.label, ax, ay - 9 * invScale);
            ctx.fillStyle = style.color;
            ctx.fillText(style.label, ax, ay - 9 * invScale);
          }
        }
      }
      ctx.restore();
    }

    _renderDeathEffects(ctx, rect, state0, state1, alpha, t0, invScale, unitDict) {
      const { ox, oy, drawW, drawH, minX, minY, spanX, spanY } = rect;
      const fxLifetime = 4.0;
      const recentDeaths = this._findDeathsInWindow(this.currentTime - fxLifetime, this.currentTime);
      if (!recentDeaths.length) return;

      const toCanvasX = (gx) => ox + ((gx - minX) / spanX) * drawW;
      const toCanvasY = (gy) => oy + (1 - (gy - minY) / spanY) * drawH;

      ctx.save();
      for (const d of recentDeaths) {
        const unitName = unitDict[d.typeId] || "Unit";
        if (this._getLayerAlpha(unitName) === 0) continue;

        const age = this.currentTime - d.timeSec;
        if (age < 0 || age > fxLifetime) continue;

        const vx = toCanvasX(d.x);
        const vy = toCanvasY(d.y);
        const victimColor = this.playersById.get(d.pid)?.color_hex || "#ffffff";
        const killerColor =
          d.killerPid !== null ? this.playersById.get(d.killerPid)?.color_hex || "#ef4444" : "#ef4444";

        // 1. Kill tracer line from killer -> victim (0..0.75s)
        if (age <= 0.75 && d.killerUid !== null) {
          let kPos = null;
          if (d.hasExplicitKillerPos) {
            if (d.killerX !== null && d.killerY !== null) {
              kPos = { x: d.killerX, y: d.killerY };
            }
          } else {
            kPos = this._resolveUnitPos(d.killerUid, state0, state1, alpha, t0);
          }
          const dist = kPos ? Math.hypot(d.x - kPos.x, d.y - kPos.y) : 0;
          if (kPos && dist > 0.4 && dist <= 20) {
            const kx = toCanvasX(kPos.x);
            const ky = toCanvasY(kPos.y);
            const tFade = 1 - age / 0.75;

            ctx.beginPath();
            ctx.moveTo(kx, ky);
            ctx.lineTo(vx, vy);
            ctx.strokeStyle = killerColor;
            ctx.globalAlpha = 0.28 * tFade;
            ctx.lineWidth = 3.2 * invScale;
            ctx.stroke();

            ctx.beginPath();
            ctx.moveTo(kx, ky);
            ctx.lineTo(vx, vy);
            ctx.strokeStyle = "#fef08a";
            ctx.globalAlpha = 0.85 * tFade;
            ctx.lineWidth = 1.1 * invScale;
            ctx.stroke();
          }
        }

        // 2. Impact shockwave ring (0..0.85s)
        if (age <= 0.85) {
          const p = age / 0.85;
          const ringR = (2.5 + p * 10.5) * invScale;
          ctx.beginPath();
          ctx.arc(vx, vy, ringR, 0, Math.PI * 2);
          ctx.strokeStyle = killerColor;
          ctx.globalAlpha = 0.85 * (1 - p);
          ctx.lineWidth = 1.8 * invScale;
          ctx.stroke();
        }

        // 3. Fading graveyard 'X' marker (0..4.0s)
        const crossFade = Math.max(0, 1 - age / fxLifetime);
        const s = 3.2 * invScale;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(vx - s, vy - s);
        ctx.lineTo(vx + s, vy + s);
        ctx.moveTo(vx + s, vy - s);
        ctx.lineTo(vx - s, vy + s);
        ctx.strokeStyle = "rgba(0, 0, 0, 0.8)";
        ctx.globalAlpha = 0.85 * crossFade;
        ctx.lineWidth = 2.8 * invScale;
        ctx.stroke();

        ctx.strokeStyle = victimColor;
        ctx.globalAlpha = 0.9 * crossFade;
        ctx.lineWidth = 1.4 * invScale;
        ctx.stroke();

        // 4. Floating loss label for high-value kills or when zoomed in (0..1.6s)
        if (age <= 1.6 && (d.value >= 150 || this.zoom >= 2.2)) {
          const lFade = 1 - age / 1.6;
          const dyOff = -6 * invScale - (age / 1.6) * 12 * invScale;
          ctx.font = `600 ${Math.round(9 * invScale)}px Inter, system-ui, sans-serif`;
          ctx.textAlign = "center";
          ctx.globalAlpha = 0.92 * lFade;
          const label = `-${unitName}`;
          ctx.lineWidth = 2.4 * invScale;
          ctx.strokeStyle = "rgba(6, 9, 15, 0.9)";
          ctx.strokeText(label, vx, vy + dyOff);
          ctx.fillStyle = "#fca5a5";
          ctx.fillText(label, vx, vy + dyOff);
        }
      }
      ctx.restore();
    }

    _bindInteractions() {
      const sig = this._abortController.signal;
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
      }, { passive: false, signal: sig });

      this.canvas.addEventListener("mousedown", (e) => {
        if (performance.now() - this._lastTouchEndMs < 450) return;
        this._cancelCameraAnim();
        dragging = true;
        moved = false;
        startX = e.clientX;
        startY = e.clientY;
      }, { signal: sig });

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
      }, { signal: sig });

      window.addEventListener("mouseup", (e) => {
        if (!dragging) return;
        dragging = false;
        if (performance.now() - this._lastTouchEndMs < 450) return;
        if (!moved) {
          const pos = getLocalXY(e.clientX, e.clientY);
          this._hitTest(pos.x, pos.y);
        }
      }, { signal: sig });

      window.addEventListener("blur", () => {
        dragging = false;
      }, { signal: sig });

      this.canvas.addEventListener("touchstart", (e) => {
        this._cancelCameraAnim();
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
      }, { passive: true, signal: sig });

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
      }, { passive: false, signal: sig });

      this.canvas.addEventListener("touchend", (e) => {
        this._lastTouchEndMs = performance.now();
        if (dragging && !moved && e.changedTouches.length === 1) {
          const pos = getLocalXY(e.changedTouches[0].clientX, e.changedTouches[0].clientY);
          this._hitTest(pos.x, pos.y);
        }
        if (e.touches.length < 2) pinchDist = 0;
        if (e.touches.length === 0) dragging = false;
      }, { signal: sig });
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

      if (best) {
        this.selectedUnitUid = best.uid;
        this.inspectedArea = null;

        let squad = [];
        if (!best.isBuilding) {
          const squadCounts = new Map();
          const squadRadius = 10;
          for (const u of this._lastRenderedUnits) {
            if (u.pid !== best.pid || u.isBuilding) continue;
            if (Math.hypot(u.ux - best.ux, u.uy - best.uy) <= squadRadius) {
              squadCounts.set(u.unitName, (squadCounts.get(u.unitName) || 0) + 1);
            }
          }
          squad = Array.from(squadCounts.entries())
            .sort((a, b) => b[1] - a[1])
            .slice(0, 6);
        }

        this.render();
        this.onUnitSelect({
          type: "unit",
          unit: best,
          ranges: getUnitRanges(best.unitName),
          squad,
        });
        return;
      }

      // Area / squad inspection when tapping near a cluster
      const { ox, oy, drawW, drawH, minX, minY, spanX, spanY } = this._getMapRect();
      const gx = minX + ((worldX - ox) / drawW) * spanX;
      const gy = minY + (1 - (worldY - oy) / drawH) * spanY;
      const areaRadius = 12;

      if (gx >= minX && gx <= minX + spanX && gy >= minY && gy <= minY + spanY) {
        const nearby = this._lastRenderedUnits.filter(
          (u) => !u.isBuilding && Math.hypot(u.ux - gx, u.uy - gy) <= areaRadius
        );
        if (nearby.length > 0) {
          this.selectedUnitUid = null;
          this.inspectedArea = { ux: gx, uy: gy, radius: areaRadius };

          const byPlayer = new Map();
          for (const u of nearby) {
            if (!byPlayer.has(u.pid)) {
              byPlayer.set(u.pid, {
                pid: u.pid,
                playerName: u.playerName,
                color: u.color,
                total: 0,
                units: new Map(),
              });
            }
            const grp = byPlayer.get(u.pid);
            grp.total += 1;
            grp.units.set(u.unitName, (grp.units.get(u.unitName) || 0) + 1);
          }

          const groups = Array.from(byPlayer.values()).map((g) => ({
            pid: g.pid,
            playerName: g.playerName,
            color: g.color,
            total: g.total,
            units: Array.from(g.units.entries()).sort((a, b) => b[1] - a[1]).slice(0, 6),
          }));

          this.render();
          this.onUnitSelect({
            type: "area",
            radius: areaRadius,
            groups,
          });
          return;
        }
      }

      this.clearSelection();
    }
  }

  global.ReplayPlayer = ReplayPlayer;
  global.resolveUnitIconPath = resolveUnitIconPath;
})(window);
