// client/src/lib/sandbox/widgetConfigs.js
//
// Per-widget sandbox configs. Each entry:
//   fields: [{ path, label, min, max, step, default, format? }]
//   presets: { [name]: { [path]: value } }
//
// Widgets not listed here fall back to a generic config (all common
// telemetry fields with sensible ranges).

const CORNER_FIELDS = (path: string, label: string) => [
  { path: `wheels.fl.${path}`, label: `FL ${label}`, min: 0, max: 1, step: 0.01, default: 0.4 },
  { path: `wheels.fr.${path}`, label: `FR ${label}`, min: 0, max: 1, step: 0.01, default: 0.4 },
  { path: `wheels.rl.${path}`, label: `RL ${label}`, min: 0, max: 1, step: 0.01, default: 0.4 },
  { path: `wheels.rr.${path}`, label: `RR ${label}`, min: 0, max: 1, step: 0.01, default: 0.4 },
]

// Shared input pedal fields reused by pedals, input_trace, steering_wheel
const INPUT_FIELDS = [
  { path: 'inputs.throttle', label: 'Throttle', min: 0, max: 1, step: 0.01, default: 0 },
  { path: 'inputs.brake',    label: 'Brake',    min: 0, max: 1, step: 0.01, default: 0 },
  { path: 'inputs.clutch',   label: 'Clutch',   min: 0, max: 1, step: 0.01, default: 0 },
]

// Shared RPM fields reused by rpm_tape, shift_coach, dyno_plot, engine_cutaway
const RPM_FIELDS = [
  { path: 'engine.rpm',     label: 'RPM',      min: 0,    max: 10000, step: 50,  default: 1000 },
  { path: 'engine.maxRpm',  label: 'Max RPM',  min: 4000, max: 12000, step: 100, default: 8000 },
  { path: 'engine.idleRpm', label: 'Idle RPM', min: 500,  max: 2000,  step: 50,  default: 900  },
]

export const CONFIGS = {
  rpm_dial: {
    fields: [
      { path: 'engine.rpm',     label: 'RPM',      min: 0,   max: 10000, step: 50, default: 1000 },
      { path: 'engine.maxRpm',  label: 'Max RPM',  min: 4000, max: 12000, step: 100, default: 8000 },
      { path: 'engine.idleRpm', label: 'Idle RPM', min: 500, max: 2000, step: 50, default: 900 },
    ],
    presets: {
      Idle:    { 'engine.rpm': 950 },
      Cruise:  { 'engine.rpm': 4200 },
      Redline: { 'engine.rpm': 7400 },
      Limiter: { 'engine.rpm': 7950 },
    },
  },
  speed_dial: {
    fields: [
      { path: 'motion.speed_mps', label: 'Speed (m/s)', min: 0, max: 110, step: 0.5, default: 0 },
    ],
    presets: {
      Stop:     { 'motion.speed_mps': 0 },
      Cruise:   { 'motion.speed_mps': 25 },
      Highway:  { 'motion.speed_mps': 50 },
      Topspeed: { 'motion.speed_mps': 95 },
    },
  },
  boost_gauge: {
    fields: [
      { path: 'engine.boost_psi', label: 'Boost (PSI)', min: 0, max: 30, step: 0.1, default: 0 },
    ],
    presets: {
      Off:    { 'engine.boost_psi': 0 },
      Spool:  { 'engine.boost_psi': 8 },
      Peak:   { 'engine.boost_psi': 22 },
      Over:   { 'engine.boost_psi': 28 },
    },
  },
  gear_display: {
    fields: [
      { path: 'drivetrain.gear', label: 'Gear', min: 0, max: 7, step: 1, default: 1 },
      { path: 'drivetrain.clutch', label: 'Clutch', min: 0, max: 1, step: 0.01, default: 0 },
    ],
    presets: {
      Reverse: { 'drivetrain.gear': 0 },
      First:   { 'drivetrain.gear': 1 },
      Top:     { 'drivetrain.gear': 6 },
      Clutch:  { 'drivetrain.gear': 3, 'drivetrain.clutch': 0.8 },
    },
  },
  grip_budget: {
    fields: [
      { path: 'derived.gripBudgetUsed', label: 'Grip used', min: 0, max: 1, step: 0.01, default: 0 },
      ...CORNER_FIELDS('combinedSlip', 'slip'),
    ],
    presets: {
      Low:    { 'derived.gripBudgetUsed': 0.15 },
      Mid:    { 'derived.gripBudgetUsed': 0.50 },
      Limit:  { 'derived.gripBudgetUsed': 0.85 },
      Over:   { 'derived.gripBudgetUsed': 1.0, 'wheels.fl.combinedSlip': 0.8, 'wheels.fr.combinedSlip': 0.6 },
    },
  },
  g_meter: {
    fields: [
      { path: 'motion.acceleration.x', label: 'Lat G (m/s²)', min: -16, max: 16, step: 0.5, default: 0 },
      { path: 'motion.acceleration.z', label: 'Long G (m/s²)', min: -16, max: 16, step: 0.5, default: 0 },
    ],
    presets: {
      Cruise:    { 'motion.acceleration.x': 0, 'motion.acceleration.z': 0 },
      Braking:   { 'motion.acceleration.x': 0, 'motion.acceleration.z': -10 },
      Cornering: { 'motion.acceleration.x': 9, 'motion.acceleration.z': 0 },
      Trail:     { 'motion.acceleration.x': 7, 'motion.acceleration.z': -6 },
    },
  },
  tire_viz: {
    fields: [
      ...CORNER_FIELDS('tireTemp_normWindow', 'temp'),
      ...CORNER_FIELDS('combinedSlip', 'slip'),
    ],
    presets: {
      Cold:    Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.tireTemp_normWindow`, 0.15])),
      Warm:    Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.tireTemp_normWindow`, 0.45])),
      Hot:     Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.tireTemp_normWindow`, 0.85])),
      Sliding: { ...Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.tireTemp_normWindow`, 0.8])),
                 'wheels.rr.combinedSlip': 0.7, 'wheels.rl.combinedSlip': 0.5 },
    },
  },
  tire_heatmap: {
    fields: [
      ...CORNER_FIELDS('tireTemp_normWindow', 'temp'),
    ],
    presets: {
      Cold:  Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.tireTemp_normWindow`, 0.15])),
      Warm:  Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.tireTemp_normWindow`, 0.45])),
      Hot:   Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.tireTemp_normWindow`, 0.85])),
      Uneven: { 'wheels.fl.tireTemp_normWindow': 0.3, 'wheels.fr.tireTemp_normWindow': 0.85,
                'wheels.rl.tireTemp_normWindow': 0.4, 'wheels.rr.tireTemp_normWindow': 0.7 },
    },
  },
  car_silhouette: {
    fields: [
      { path: 'motion.speed_mps', label: 'Speed (m/s)', min: 0, max: 110, step: 1, default: 0 },
      { path: 'motion.acceleration.x', label: 'Lat G (m/s²)', min: -16, max: 16, step: 0.5, default: 0 },
      { path: 'motion.acceleration.z', label: 'Long G (m/s²)', min: -16, max: 16, step: 0.5, default: 0 },
      { path: 'derived.weightFront', label: 'Weight front', min: 0, max: 1, step: 0.01, default: 0.5 },
      { path: 'derived.weightLeft', label: 'Weight left', min: 0, max: 1, step: 0.01, default: 0.5 },
      ...CORNER_FIELDS('combinedSlip', 'slip'),
    ],
    presets: {
      Cruise:    { 'motion.speed_mps': 25, 'derived.weightFront': 0.5, 'derived.weightLeft': 0.5 },
      Braking:   { 'motion.speed_mps': 20, 'motion.acceleration.z': -10, 'derived.weightFront': 0.7 },
      Cornering: { 'motion.speed_mps': 30, 'motion.acceleration.x': 12, 'derived.weightLeft': 0.25,
                   'wheels.fr.combinedSlip': 0.3, 'wheels.rr.combinedSlip': 0.3 },
      Drift:     { 'motion.speed_mps': 25, 'motion.acceleration.x': 13, 'derived.weightLeft': 0.2,
                   'wheels.rl.combinedSlip': 0.8, 'wheels.rr.combinedSlip': 0.85,
                   'wheels.fl.combinedSlip': 0.2, 'wheels.fr.combinedSlip': 0.2 },
    },
  },
  tire_wear: {
    fields: [
      { path: 'modeled.tireWearConfidence', label: 'Confidence', min: 0, max: 1, step: 0.05, default: 0.6 },
      { path: 'modeled.tireWear.fl', label: 'FL wear', min: 0, max: 1, step: 0.01, default: 0.1 },
      { path: 'modeled.tireWear.fr', label: 'FR wear', min: 0, max: 1, step: 0.01, default: 0.1 },
      { path: 'modeled.tireWear.rl', label: 'RL wear', min: 0, max: 1, step: 0.01, default: 0.1 },
      { path: 'modeled.tireWear.rr', label: 'RR wear', min: 0, max: 1, step: 0.01, default: 0.1 },
    ],
    presets: {
      Fresh:       { 'modeled.tireWear.fl': 0.05, 'modeled.tireWear.fr': 0.05, 'modeled.tireWear.rl': 0.05, 'modeled.tireWear.rr': 0.05 },
      Mid:         { 'modeled.tireWear.fl': 0.4,  'modeled.tireWear.fr': 0.4,  'modeled.tireWear.rl': 0.4,  'modeled.tireWear.rr': 0.4 },
      Worn:        { 'modeled.tireWear.fl': 0.75, 'modeled.tireWear.fr': 0.7,  'modeled.tireWear.rl': 0.8,  'modeled.tireWear.rr': 0.85 },
      Calibrating: { 'modeled.tireWearConfidence': 0.02 },
    },
  },
  suspension_viz: {
    fields: [
      ...CORNER_FIELDS('suspensionTravel_norm', 'travel'),
    ],
    presets: {
      Level:      Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.suspensionTravel_norm`, 0.5])),
      'Nose Dive': { 'wheels.fl.suspensionTravel_norm': 0.85, 'wheels.fr.suspensionTravel_norm': 0.85,
                    'wheels.rl.suspensionTravel_norm': 0.2,  'wheels.rr.suspensionTravel_norm': 0.2 },
      Roll:        { 'wheels.fl.suspensionTravel_norm': 0.2, 'wheels.fr.suspensionTravel_norm': 0.8,
                    'wheels.rl.suspensionTravel_norm': 0.2, 'wheels.rr.suspensionTravel_norm': 0.8 },
      Airtime:     Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.suspensionTravel_norm`, 0])),
    },
  },
  lap_timer: {
    fields: [
      { path: 'race.currentLapS', label: 'Current lap (s)', min: 0, max: 300, step: 0.1, default: 45.5 },
      { path: 'race.lastLapS',    label: 'Last lap (s)',    min: 0, max: 300, step: 0.1, default: 92.345 },
      { path: 'race.bestLapS',    label: 'Best lap (s)',    min: 0, max: 300, step: 0.1, default: 91.812 },
    ],
    presets: {
      'No laps':     { 'race.currentLapS': 12.3,  'race.lastLapS': null, 'race.bestLapS': null },
      Normal:        { 'race.currentLapS': 45.5,  'race.lastLapS': 92.345, 'race.bestLapS': 91.812 },
      'Slower last': { 'race.currentLapS': 45.5,  'race.lastLapS': 93.5,   'race.bestLapS': 91.812 },
      'New PB!':     { 'race.currentLapS': 10.0,  'race.lastLapS': 90.5,   'race.bestLapS': 90.5 },
    },
  },
  finish_predict: {
    fields: [
      { path: 'mock.finish.position',    label: 'Predicted position', min: 1, max: 24, step: 1, default: 2 },
      { path: 'mock.finish.wasPosition', label: 'Previous position',  min: 1, max: 24, step: 1, default: 3 },
    ],
    presets: {
      Climbing:   { 'mock.finish.position': 2, 'mock.finish.wasPosition': 6 },
      Holding:    { 'mock.finish.position': 4, 'mock.finish.wasPosition': 4 },
      Slipping:   { 'mock.finish.position': 7, 'mock.finish.wasPosition': 3 },
      'On podium': { 'mock.finish.position': 3, 'mock.finish.wasPosition': 5 },
      Winning:    { 'mock.finish.position': 1, 'mock.finish.wasPosition': 2 },
    },
    apiMocks: {
      predictFinish: (vals: Record<string, any>) => ({
        position: Math.round(vals['mock.finish.position'] ?? 2),
        wasPosition: Math.round(vals['mock.finish.wasPosition'] ?? 3),
        overtake: null,  // FH6 has no opponent telemetry
      }),
    },
  },
  crash_risk: {
    fields: [
      { path: 'mock.crash.risk',       label: 'Risk',        min: 0, max: 1,  step: 0.01, default: 0.15 },
      { path: 'mock.crash.withinLaps', label: 'Within laps', min: 0, max: 20, step: 1,    default: 4 },
    ],
    presets: {
      Low:      { 'mock.crash.risk': 0.08, 'mock.crash.reason': 'No elevated pattern', 'mock.crash.withinLaps': 0 },
      Elevated: { 'mock.crash.risk': 0.45, 'mock.crash.reason': 'T11 oversteer pattern', 'mock.crash.withinLaps': 4 },
      High:     { 'mock.crash.risk': 0.78, 'mock.crash.reason': 'Lockup pattern T7', 'mock.crash.withinLaps': 1 },
      Critical: { 'mock.crash.risk': 0.95, 'mock.crash.reason': 'Wall in turn 11', 'mock.crash.withinLaps': 0 },
    },
    apiMocks: {
      predictCrash: (vals: Record<string, any>) => ({
        risk: vals['mock.crash.risk'] ?? 0.15,
        elevatedReason: vals['mock.crash.reason'] ?? 'T11 oversteer pattern',
        etaCorner: 'T11',
        withinLaps: vals['mock.crash.withinLaps'] ?? 4,
      }),
    },
  },
  tire_failure: {
    fields: [
      { path: 'mock.tireFail.fl.wear', label: 'FL wear', min: 0, max: 1, step: 0.01, default: 0.31 },
      { path: 'mock.tireFail.fr.wear', label: 'FR wear', min: 0, max: 1, step: 0.01, default: 0.34 },
      { path: 'mock.tireFail.rl.wear', label: 'RL wear', min: 0, max: 1, step: 0.01, default: 0.48 },
      { path: 'mock.tireFail.rr.wear', label: 'RR wear', min: 0, max: 1, step: 0.01, default: 0.53 },
      { path: 'mock.tireFail.fl.lap',  label: 'FL fails @ lap', min: 0, max: 60, step: 1, default: 24 },
      { path: 'mock.tireFail.fr.lap',  label: 'FR fails @ lap', min: 0, max: 60, step: 1, default: 22 },
      { path: 'mock.tireFail.rl.lap',  label: 'RL fails @ lap', min: 0, max: 60, step: 1, default: 15 },
      { path: 'mock.tireFail.rr.lap',  label: 'RR fails @ lap', min: 0, max: 60, step: 1, default: 13 },
    ],
    presets: {
      Fresh: {
        'mock.tireFail.fl.wear': 0.05, 'mock.tireFail.fr.wear': 0.05,
        'mock.tireFail.rl.wear': 0.05, 'mock.tireFail.rr.wear': 0.05,
        'mock.tireFail.fl.lap': 50, 'mock.tireFail.fr.lap': 50,
        'mock.tireFail.rl.lap': 50, 'mock.tireFail.rr.lap': 50,
      },
      Mid: {
        'mock.tireFail.fl.wear': 0.35, 'mock.tireFail.fr.wear': 0.38,
        'mock.tireFail.rl.wear': 0.45, 'mock.tireFail.rr.wear': 0.50,
      },
      'RR worn': {
        'mock.tireFail.fl.wear': 0.31, 'mock.tireFail.fr.wear': 0.34,
        'mock.tireFail.rl.wear': 0.48, 'mock.tireFail.rr.wear': 0.85,
        'mock.tireFail.rr.lap': 3,
      },
      Healthy: { 'mock.tireFail.fl.wear': 0.10, 'mock.tireFail.fr.wear': 0.10, 'mock.tireFail.rl.wear': 0.10, 'mock.tireFail.rr.wear': 0.10 },
    },
    apiMocks: {
      predictTireFailure: (vals: Record<string, any>) => {
        const corner = (k: string) => ({
          wear: vals[`mock.tireFail.${k}.wear`] ?? 0,
          failureAtLap: vals[`mock.tireFail.${k}.lap`] ?? null,
          confidence: 0.78,
        })
        const perCorner = { fl: corner('fl'), fr: corner('fr'), rl: corner('rl'), rr: corner('rr') }
        // limiting corner = one with lowest failureAtLap (most urgent)
        const limitingCorner = Object.entries(perCorner)
          .filter(([_, v]) => v.failureAtLap != null)
          .sort((a, b) => (a[1].failureAtLap ?? Infinity) - (b[1].failureAtLap ?? Infinity))[0]?.[0] ?? null
        return { perCorner, limitingCorner, modelVersion: 'tire-wear-v0-mock', inputs: ['mock'] }
      },
    },
  },

  // ── New configs ────────────────────────────────────────────────────────

  rpm_tape: {
    fields: [...RPM_FIELDS],
    presets: {
      Idle:    { 'engine.rpm': 950 },
      Cruise:  { 'engine.rpm': 4200 },
      Redline: { 'engine.rpm': 7400 },
      Limiter: { 'engine.rpm': 7950 },
    },
  },

  dyno_plot: {
    fields: [
      ...RPM_FIELDS,
      { path: 'engine.power_w',   label: 'Power (W)',    min: 0, max: 350000, step: 1000, default: 50000 },
      { path: 'engine.torque_nm', label: 'Torque (N·m)', min: 0, max: 800,    step: 5,    default: 200 },
    ],
    presets: {
      Idle:    { 'engine.rpm': 950,  'engine.power_w': 5000,   'engine.torque_nm': 80  },
      Cruise:  { 'engine.rpm': 3500, 'engine.power_w': 80000,  'engine.torque_nm': 320 },
      Peak:    { 'engine.rpm': 6000, 'engine.power_w': 220000, 'engine.torque_nm': 500 },
      Redline: { 'engine.rpm': 7500, 'engine.power_w': 185000, 'engine.torque_nm': 350 },
    },
    notes: 'DynoPlot builds its curve by sampling peak power/torque at each RPM bin over time. Use the animate checkbox on RPM to sweep through the rev range and build the curve.',
  },

  input_trace: {
    fields: [
      ...INPUT_FIELDS,
      { path: 'inputs.steer', label: 'Steer', min: -1, max: 1, step: 0.01, default: 0 },
    ],
    presets: {
      Idle:      { 'inputs.throttle': 0,    'inputs.brake': 0,    'inputs.clutch': 0, 'inputs.steer': 0    },
      FullThrottle: { 'inputs.throttle': 1, 'inputs.brake': 0,    'inputs.clutch': 0, 'inputs.steer': 0    },
      Braking:   { 'inputs.throttle': 0,    'inputs.brake': 0.85, 'inputs.clutch': 0, 'inputs.steer': 0    },
      Cornering: { 'inputs.throttle': 0.4,  'inputs.brake': 0,    'inputs.clutch': 0, 'inputs.steer': 0.6  },
      Shifting:  { 'inputs.throttle': 0.8,  'inputs.brake': 0,    'inputs.clutch': 0.9, 'inputs.steer': 0  },
    },
  },

  slip_warning: {
    fields: [
      ...CORNER_FIELDS('combinedSlip', 'slip'),
    ],
    presets: {
      Grip:    Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.combinedSlip`, 0.05])),
      Sliding: { 'wheels.fl.combinedSlip': 0.2, 'wheels.fr.combinedSlip': 0.25, 'wheels.rl.combinedSlip': 0.3, 'wheels.rr.combinedSlip': 0.28 },
      Spin:    { 'wheels.fl.combinedSlip': 0.1, 'wheels.fr.combinedSlip': 0.1,  'wheels.rl.combinedSlip': 0.7, 'wheels.rr.combinedSlip': 0.75 },
      'Full Spin': Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.combinedSlip`, 0.8])),
    },
  },

  world_map: {
    fields: [
      { path: 'motion.speed_mps',       label: 'Speed (m/s)',  min: 0,   max: 110, step: 0.5, default: 0    },
      { path: 'motion.acceleration.x',  label: 'Lat G (m/s²)', min: -16, max: 16,  step: 0.5, default: 0    },
      { path: 'motion.acceleration.z',  label: 'Long G (m/s²)',min: -16, max: 16,  step: 0.5, default: 0    },
      { path: 'motion.position.x',      label: 'World X',      min: -10000, max: 10000, step: 10, default: 0 },
      { path: 'motion.position.z',      label: 'World Z',      min: -10000, max: 10000, step: 10, default: 0 },
      { path: 'inputs.throttle',        label: 'Throttle',     min: 0,   max: 1,   step: 0.01, default: 0   },
      { path: 'inputs.brake',           label: 'Brake',        min: 0,   max: 1,   step: 0.01, default: 0   },
    ],
    presets: {
      Stopped: { 'motion.speed_mps': 0, 'inputs.throttle': 0, 'inputs.brake': 0 },
      Driving: { 'motion.speed_mps': 30, 'inputs.throttle': 0.6, 'inputs.brake': 0 },
      Braking: { 'motion.speed_mps': 20, 'motion.acceleration.z': -8, 'inputs.throttle': 0, 'inputs.brake': 0.9 },
      Cornering: { 'motion.speed_mps': 25, 'motion.acceleration.x': 10, 'inputs.throttle': 0.4 },
    },
    notes: 'WorldMap requires calibration and tile assets to show the map. The sandbox frame override sets position/speed; the tile server and calibration UI work independently.',
  },

  coach_feed: {
    fields: [
      { path: 'mock.coach.count', label: 'Callouts', min: 0, max: 6, step: 1, default: 3 },
    ],
    presets: {
      None: { 'mock.coach.count': 0 },
      Few:  { 'mock.coach.count': 2 },
      Many: { 'mock.coach.count': 6 },
    },
    // CoachFeed subscribes to /ws/coach 'callout' events. Inject fake
    // callouts via the sandbox's WS emit hook. Oldest first so they
    // appear newest-on-top in the widget (it prepends).
    wsEmit: (vals: Record<string, any>) => {
      const n = Math.round(vals['mock.coach.count'] ?? 3)
      const SAMPLES = [
        { priority: 'tip',  text: 'You brake 4m early into T3. Try a later marker.', lap: 5, corner: 'T3' },
        { priority: 'warn', text: 'Slid out at T11 a few times. Throttle is too aggressive on exit.', lap: 7, corner: 'T11' },
        { priority: 'info', text: 'Tires are warmed up — push now.', lap: 3, corner: '' },
        { priority: 'tip',  text: 'Downshift a beat later into T5 — engine braking will help rotate.', lap: 6, corner: 'T5' },
        { priority: 'warn', text: 'Big lockup at T7. Ease off the brake before turn-in.', lap: 8, corner: 'T7' },
        { priority: 'info', text: 'New best sector 2.', lap: 7, corner: '' },
      ]
      return SAMPLES.slice(0, n).map((s, i) => ({
        channel: 'coach',
        type: 'callout',
        payload: {
          id: `cb_${i}`,
          atS: i * 4,
          priority: s.priority,
          text: s.text,
          lap: s.lap,
          corner: s.corner,
          lapContext: { lap: s.lap, corner: s.corner },
        },
      }))
    },
  },

  pedals: {
    fields: [
      ...INPUT_FIELDS,
      { path: 'inputs.handbrake', label: 'Handbrake', min: 0, max: 1, step: 0.01, default: 0 },
    ],
    presets: {
      Idle:         { 'inputs.throttle': 0,    'inputs.brake': 0,    'inputs.clutch': 0, 'inputs.handbrake': 0 },
      FullThrottle: { 'inputs.throttle': 1.0,  'inputs.brake': 0,    'inputs.clutch': 0, 'inputs.handbrake': 0 },
      Braking:      { 'inputs.throttle': 0,    'inputs.brake': 0.9,  'inputs.clutch': 0, 'inputs.handbrake': 0 },
      Shifting:     { 'inputs.throttle': 0.7,  'inputs.brake': 0,    'inputs.clutch': 0.95, 'inputs.handbrake': 0 },
      Handbrake:    { 'inputs.throttle': 0.3,  'inputs.brake': 0,    'inputs.clutch': 0, 'inputs.handbrake': 1 },
    },
  },

  lap_predict: {
    fields: [
      { path: 'mock.lapPred.base',   label: 'Base lap time (s)', min: 50, max: 150, step: 0.5, default: 68.6 },
      { path: 'mock.lapPred.spread', label: 'Lap-to-lap spread', min: 0,  max: 5,   step: 0.1, default: 0.8 },
      { path: 'mock.lapPred.confidence', label: 'Confidence',   min: 0,  max: 1,   step: 0.05, default: 0.78 },
    ],
    presets: {
      Tight:      { 'mock.lapPred.base': 68.6, 'mock.lapPred.spread': 0.3, 'mock.lapPred.confidence': 0.92 },
      Normal:     { 'mock.lapPred.base': 68.6, 'mock.lapPred.spread': 0.8, 'mock.lapPred.confidence': 0.78 },
      'Tires fading': { 'mock.lapPred.base': 70.2, 'mock.lapPred.spread': 2.5, 'mock.lapPred.confidence': 0.45 },
    },
    apiMocks: {
      predictLap: (vals: Record<string, any>, n: number = 5) => {
        const base   = vals['mock.lapPred.base'] ?? 68.6
        const spread = vals['mock.lapPred.spread'] ?? 0.8
        const conf   = vals['mock.lapPred.confidence'] ?? 0.78
        const predictions = []
        for (let i = 0; i < n; i++) {
          const drift = i * 0.15
          const t = base + drift
          predictions.push({
            lap: 9 + i,
            time_s: t,
            lower_s: t - spread,
            upper_s: t + spread,
            confidence: Math.max(0.1, conf - i * 0.06),
          })
        }
        return {
          predictedAt: Date.now() / 1000,
          modelVersion: 'lap-residual-v2.1-mock',
          predictions,
          limiter: 'rr_tire_degradation',
          inputs: ['mock'],
        }
      },
    },
  },

  session_summary: {
    fields: [
      { path: 'mock.session.lapCount',     label: 'Lap count',     min: 0,   max: 50,  step: 1,   default: 7 },
      { path: 'mock.session.bestLapS',     label: 'Best lap (s)',  min: 50,  max: 200, step: 0.1, default: 91.812 },
      { path: 'mock.session.durationS',    label: 'Duration (s)',  min: 60,  max: 7200, step: 30, default: 720 },
      { path: 'mock.session.topSpeedMps',  label: 'Top speed m/s', min: 0,   max: 120, step: 1,   default: 78 },
      { path: 'mock.session.distanceM',    label: 'Distance (m)',  min: 0,   max: 100000, step: 100, default: 14200 },
    ],
    presets: {
      Short:  { 'mock.session.lapCount': 3,  'mock.session.durationS': 240,  'mock.session.distanceM': 5800 },
      Normal: { 'mock.session.lapCount': 7,  'mock.session.durationS': 720,  'mock.session.distanceM': 14200 },
      Long:   { 'mock.session.lapCount': 28, 'mock.session.durationS': 2820, 'mock.session.distanceM': 58000 },
    },
    apiMocks: {
      sessionDetail: (vals: Record<string, any>) => ({
        id: 'sandbox-session',
        name: 'Sandbox session',
        type: 'practice',
        durationS: vals['mock.session.durationS'] ?? 720,
        lapCount: Math.round(vals['mock.session.lapCount'] ?? 7),
        bestLapS: vals['mock.session.bestLapS'] ?? 91.812,
        topSpeedMps: vals['mock.session.topSpeedMps'] ?? 78,
        distanceM: vals['mock.session.distanceM'] ?? 14200,
        lapRollups: [],
        events: [],
      }),
    },
  },

  fingerprint: {
    fields: [
      { path: 'mock.driver.smooth',   label: 'Smooth',   min: 0, max: 1, step: 0.01, default: 0.78 },
      { path: 'mock.driver.brave',    label: 'Brave',    min: 0, max: 1, step: 0.01, default: 0.55 },
      { path: 'mock.driver.early',    label: 'Early',    min: 0, max: 1, step: 0.01, default: 0.38 },
      { path: 'mock.driver.patient',  label: 'Patient',  min: 0, max: 1, step: 0.01, default: 0.62 },
      { path: 'mock.driver.precise',  label: 'Precise',  min: 0, max: 1, step: 0.01, default: 0.82 },
      { path: 'mock.driver.consist',  label: 'Consistent', min: 0, max: 1, step: 0.01, default: 0.50 },
    ],
    presets: {
      Balanced:   { 'mock.driver.smooth': 0.6, 'mock.driver.brave': 0.6, 'mock.driver.early': 0.5, 'mock.driver.patient': 0.6, 'mock.driver.precise': 0.6, 'mock.driver.consist': 0.6 },
      Aggressive: { 'mock.driver.smooth': 0.3, 'mock.driver.brave': 0.92, 'mock.driver.early': 0.15, 'mock.driver.patient': 0.25, 'mock.driver.precise': 0.55, 'mock.driver.consist': 0.45 },
      Smooth:     { 'mock.driver.smooth': 0.95, 'mock.driver.brave': 0.45, 'mock.driver.early': 0.6, 'mock.driver.patient': 0.85, 'mock.driver.precise': 0.88, 'mock.driver.consist': 0.78 },
      Erratic:    { 'mock.driver.smooth': 0.35, 'mock.driver.brave': 0.62, 'mock.driver.early': 0.42, 'mock.driver.patient': 0.30, 'mock.driver.precise': 0.42, 'mock.driver.consist': 0.18 },
    },
    apiMocks: {
      driverProfile: (vals: Record<string, any>) => ({
        lapsAnalyzed: 412,
        fingerprint: {
          smooth:  vals['mock.driver.smooth']  ?? 0.78,
          brave:   vals['mock.driver.brave']   ?? 0.55,
          early:   vals['mock.driver.early']   ?? 0.38,
          patient: vals['mock.driver.patient'] ?? 0.62,
          precise: vals['mock.driver.precise'] ?? 0.82,
          consist: vals['mock.driver.consist'] ?? 0.50,
        },
        fingerprintBaseline_90d: { smooth: 0.55, brave: 0.55, early: 0.55, patient: 0.55, precise: 0.55, consist: 0.55 },
        traits: [
          { id: 'late_braker', name: 'Late braker', score: 0.86, blurb: 'Holds the brake deep' },
          { id: 'smooth_hands', name: 'Smooth hands', score: 0.78, blurb: 'Minimal mid-corner correction' },
        ],
        strengths: ['smooth steering', 'trail-braking', 'throttle on exit'],
        weaknesses: ['slow corners', 'downshift timing'],
        carAgnosticShare: 0.72,
        persona: 'Smooth late-braker who muscles the throttle on exit. Consistent and improving.',
        personaUpdatedAt: new Date().toISOString(),
      }),
    },
  },

  style_drift: {
    fields: [
      { path: 'mock.styleDrift.smooth_delta',  label: 'Smooth Δ',   min: -0.4, max: 0.4, step: 0.01, default: 0.23 },
      { path: 'mock.styleDrift.brave_delta',   label: 'Brave Δ',    min: -0.4, max: 0.4, step: 0.01, default: 0.00 },
      { path: 'mock.styleDrift.early_delta',   label: 'Early Δ',    min: -0.4, max: 0.4, step: 0.01, default: -0.17 },
      { path: 'mock.styleDrift.patient_delta', label: 'Patient Δ',  min: -0.4, max: 0.4, step: 0.01, default: 0.07 },
      { path: 'mock.styleDrift.precise_delta', label: 'Precise Δ',  min: -0.4, max: 0.4, step: 0.01, default: 0.27 },
      { path: 'mock.styleDrift.consist_delta', label: 'Consist Δ',  min: -0.4, max: 0.4, step: 0.01, default: -0.05 },
    ],
    presets: {
      Stable:    Object.fromEntries(['smooth','brave','early','patient','precise','consist'].map(k => [`mock.styleDrift.${k}_delta`, 0])),
      Improving: { 'mock.styleDrift.smooth_delta': 0.20, 'mock.styleDrift.precise_delta': 0.25, 'mock.styleDrift.consist_delta': 0.15 },
      Regressing:{ 'mock.styleDrift.smooth_delta': -0.18, 'mock.styleDrift.consist_delta': -0.25, 'mock.styleDrift.precise_delta': -0.12 },
    },
    apiMocks: {
      driverProfile: (vals: Record<string, any>) => {
        const baseline: Record<string, number> = { smooth: 0.55, brave: 0.55, early: 0.55, patient: 0.55, precise: 0.55, consist: 0.55 }
        const fp: Record<string, number> = {}
        for (const k of Object.keys(baseline)) {
          fp[k] = Math.max(0, Math.min(1, baseline[k]! + (vals[`mock.styleDrift.${k}_delta`] ?? 0)))
        }
        return {
          lapsAnalyzed: 412,
          fingerprint: fp,
          fingerprintBaseline_90d: baseline,
          traits: [],
          strengths: [],
          weaknesses: [],
          carAgnosticShare: 0.72,
          persona: '',
          personaUpdatedAt: new Date().toISOString(),
        }
      },
    },
  },

  shift_coach: {
    fields: [
      ...RPM_FIELDS,
      { path: 'drivetrain.gear', label: 'Gear', min: 0, max: 7, step: 1, default: 3 },
    ],
    presets: {
      Idle:    { 'engine.rpm': 950,  'drivetrain.gear': 1 },
      Cruise:  { 'engine.rpm': 4000, 'drivetrain.gear': 3 },
      Buildup: { 'engine.rpm': 6500, 'drivetrain.gear': 3 },
      Redline: { 'engine.rpm': 7800, 'drivetrain.gear': 3 },
    },
    notes: 'ShiftCoach also listens for missed_upshift events via the live event stream, which the sandbox cannot emit. The missed-shift counter will stay at 0.',
  },

  highlight_reel: {
    fields: [
      { path: 'mock.events.count', label: 'Event count', min: 0, max: 12, step: 1, default: 6 },
    ],
    presets: {
      None: { 'mock.events.count': 0 },
      Few:  { 'mock.events.count': 3 },
      Many: { 'mock.events.count': 12 },
    },
    apiMocks: {
      sessionDetail: (vals: Record<string, any>) => {
        const n = Math.round(vals['mock.events.count'] ?? 6)
        const KINDS = ['lap_completed', 'best_lap', 'spin', 'oversteer', 'off_track', 'gear_skip']
        const events = []
        for (let i = 0; i < n; i++) {
          events.push({
            id: `evt_${i}`,
            kind: KINDS[i % KINDS.length],
            atS: i * 35 + 10,
            lap: 1 + Math.floor(i / 2),
            corner: ['T1', 'T3', 'T7', 'T11'][i % 4],
            text: ['New best lap', 'Rear stepped out', 'Off-track at exit', 'Aggressive shift'][i % 4],
          })
        }
        return {
          id: 'sandbox-session',
          name: 'Sandbox',
          events,
          lapRollups: [],
        }
      },
    },
  },

  physics_insights: {
    fields: [
      { path: 'derived.gripBudgetUsed',     label: 'Grip used',     min: 0, max: 1,  step: 0.01, default: 0.2  },
      { path: 'derived.bodyControl',        label: 'Body control',  min: 0, max: 1,  step: 0.01, default: 0.5  },
      { path: 'derived.balance',            label: 'Balance',       min: -1, max: 1, step: 0.01, default: 0.0  },
      { path: 'derived.throttleSmoothness', label: 'Thr. smooth',   min: 0, max: 1,  step: 0.01, default: 0.6  },
      { path: 'derived.weightFront',        label: 'Weight front',  min: 0, max: 1,  step: 0.01, default: 0.5  },
      { path: 'derived.weightLeft',         label: 'Weight left',   min: 0, max: 1,  step: 0.01, default: 0.5  },
    ],
    presets: {
      Cruise:    { 'derived.gripBudgetUsed': 0.15, 'derived.bodyControl': 0.8, 'derived.balance': 0.05, 'derived.throttleSmoothness': 0.75 },
      Cornering: { 'derived.gripBudgetUsed': 0.7,  'derived.bodyControl': 0.5, 'derived.balance': -0.3, 'derived.throttleSmoothness': 0.4,
                   'derived.weightFront': 0.45, 'derived.weightLeft': 0.3 },
      Braking:   { 'derived.gripBudgetUsed': 0.6,  'derived.bodyControl': 0.4, 'derived.balance': 0.35, 'derived.throttleSmoothness': 0.2,
                   'derived.weightFront': 0.7 },
      Limit:     { 'derived.gripBudgetUsed': 0.95, 'derived.bodyControl': 0.2, 'derived.balance': -0.6, 'derived.throttleSmoothness': 0.15 },
    },
  },

  position_tracker: {
    fields: [
      { path: 'race.position', label: 'Position', min: 1, max: 24, step: 1, default: 8 },
    ],
    presets: {
      Leading:  { 'race.position': 1  },
      Midfield: { 'race.position': 8  },
      Backmarker: { 'race.position': 20 },
    },
  },

  car_badge: {
    fields: [
      // No numeric sliders — use presets to pick the car
    ],
    // Default to the Lambo preset on widget mount so the user doesn't have
    // to click a preset to see the widget populated.
    defaults: {
      'mock.car.id': 'car_lambo_svj',
      'mock.car.name': 'Lamborghini Aventador SVJ',
      'mock.car.class': 'S',
      'mock.car.pi': 920,
      'mock.car.drivetrain': 'AWD',
      'frame.carId': 'car_lambo_svj',
    },
    presets: {
      Lambo:    { 'mock.car.id': 'car_lambo_svj', 'mock.car.name': 'Lamborghini Aventador SVJ', 'mock.car.class': 'S', 'mock.car.pi': 920, 'mock.car.drivetrain': 'AWD', 'frame.carId': 'car_lambo_svj' },
      Porsche:  { 'mock.car.id': 'car_911_gt3',   'mock.car.name': 'Porsche 911 GT3',           'mock.car.class': 'A', 'mock.car.pi': 825, 'mock.car.drivetrain': 'RWD', 'frame.carId': 'car_911_gt3' },
      Subaru:   { 'mock.car.id': 'car_wrx_sti',   'mock.car.name': 'Subaru WRX STI',            'mock.car.class': 'B', 'mock.car.pi': 605, 'mock.car.drivetrain': 'AWD', 'frame.carId': 'car_wrx_sti' },
      Unknown:  { 'mock.car.id': 'car_unknown',   'mock.car.name': 'Car #2451',                  'mock.car.class': '?', 'mock.car.pi': 0,   'mock.car.drivetrain': '?',   'frame.carId': 'car_unknown' },
    },
    apiMocks: {
      listCars: (vals: Record<string, any>) => ({
        cars: [
          {
            id: vals['mock.car.id'] ?? 'car_lambo_svj',
            displayName: vals['mock.car.name'] ?? 'Lamborghini Aventador SVJ',
            shortName: (vals['mock.car.name'] ?? 'Aventador SVJ').replace(/^\d{4}\s*/, ''),
            carOrdinal: 2451,
            carClass: vals['mock.car.class'] ?? 'S',
            performanceIndex: Math.round(vals['mock.car.pi'] ?? 920),
            drivetrain: vals['mock.car.drivetrain'] ?? 'AWD',
            sessionCount: 9,
            totalSecondsDriven: 15120,
            bestLapByTrack: {},
          },
        ],
      }),
    },
  },

  stint_timer: {
    fields: [
      { path: 'race.raceTimeS', label: 'Race time (s)', min: 0, max: 7200, step: 10, default: 0 },
    ],
    presets: {
      Start:   { 'race.raceTimeS': 0    },
      Fresh:   { 'race.raceTimeS': 600  },
      Mid:     { 'race.raceTimeS': 1800 },
      Long:    { 'race.raceTimeS': 3600 },
    },
  },

  engine_cutaway: {
    fields: [
      ...RPM_FIELDS,
      { path: 'engine.boost_psi',    label: 'Boost (PSI)',  min: 0, max: 30, step: 0.5, default: 0 },
      { path: 'world.numCylinders',  label: 'Cylinders',    min: 3, max: 12, step: 1,   default: 4 },
    ],
    presets: {
      Off:      { 'engine.rpm': 0,    'engine.boost_psi': 0  },
      Idle:     { 'engine.rpm': 950,  'engine.boost_psi': 0,  'world.numCylinders': 4 },
      Cruise:   { 'engine.rpm': 3500, 'engine.boost_psi': 5,  'world.numCylinders': 4 },
      V8Redline:{ 'engine.rpm': 7500, 'engine.boost_psi': 0,  'world.numCylinders': 8 },
      TurboMax: { 'engine.rpm': 6000, 'engine.boost_psi': 25, 'world.numCylinders': 4 },
    },
  },

  power_flow: {
    fields: [
      { path: 'engine.power_w',   label: 'Power (W)',    min: 0, max: 350000, step: 1000, default: 50000 },
      { path: 'engine.torque_nm', label: 'Torque (N·m)', min: 0, max: 800,    step: 5,    default: 200   },
      { path: 'drivetrain.type',  label: 'Drivetrain',   min: 0, max: 2,      step: 1,    default: 0     },
      ...CORNER_FIELDS('combinedSlip', 'slip'),
    ],
    presets: {
      'AWD Idle':    { 'engine.power_w': 5000,   'drivetrain.type': 'AWD', ...Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.combinedSlip`, 0])) },
      'AWD Cruise':  { 'engine.power_w': 100000, 'drivetrain.type': 'AWD', ...Object.fromEntries(['fl','fr','rl','rr'].map(k => [`wheels.${k}.combinedSlip`, 0.05])) },
      'RWD Slip':    { 'engine.power_w': 200000, 'drivetrain.type': 'RWD', 'wheels.rl.combinedSlip': 0.5, 'wheels.rr.combinedSlip': 0.55 },
      'FWD Cruise':  { 'engine.power_w': 80000,  'drivetrain.type': 'FWD', 'wheels.fl.combinedSlip': 0.05, 'wheels.fr.combinedSlip': 0.05 },
    },
    notes: 'The drivetrain slider is a 0–2 index mapped internally by the widget. For correct presets, use the preset buttons which pass the "AWD"/"RWD"/"FWD" string directly.',
  },

  race_stats: {
    fields: [
      { path: 'race.position',  label: 'Position',     min: 1,   max: 24,  step: 1,   default: 8    },
      { path: 'race.lap',       label: 'Lap',          min: 1,   max: 100, step: 1,   default: 1    },
      { path: 'race.raceTimeS', label: 'Race time (s)',min: 0,   max: 7200,step: 10,  default: 0    },
      { path: 'motion.speed_mps', label: 'Speed (m/s)',min: 0,   max: 110, step: 0.5, default: 0    },
    ],
    presets: {
      Start:    { 'race.position': 3, 'race.lap': 1, 'race.raceTimeS': 30,  'motion.speed_mps': 20 },
      Midrace:  { 'race.position': 5, 'race.lap': 8, 'race.raceTimeS': 900, 'motion.speed_mps': 55 },
      Leading:  { 'race.position': 1, 'race.lap': 5, 'race.raceTimeS': 600, 'motion.speed_mps': 80 },
    },
  },

  steering_wheel: {
    fields: [
      { path: 'inputs.steer', label: 'Steer (-1=L, +1=R)', min: -1, max: 1, step: 0.01, default: 0 },
    ],
    presets: {
      Centre:     { 'inputs.steer': 0    },
      'Right 45°': { 'inputs.steer': 0.33 },
      'Full Right': { 'inputs.steer': 1.0 },
      'Full Left':  { 'inputs.steer': -1.0 },
    },
  },

  lap_compare: {
    fields: [
      { path: 'race.lastLapS', label: 'Last lap (s)', min: 0, max: 300, step: 0.1, default: 92.345 },
      { path: 'race.bestLapS', label: 'Best lap (s)', min: 0, max: 300, step: 0.1, default: 91.812 },
    ],
    presets: {
      'No data':    { 'race.lastLapS': 0,      'race.bestLapS': 0      },
      'First lap':  { 'race.lastLapS': 95.0,   'race.bestLapS': 95.0   },
      'Improving':  { 'race.lastLapS': 91.5,   'race.bestLapS': 91.812 },
      'Slower lap': { 'race.lastLapS': 93.5,   'race.bestLapS': 91.812 },
      'New PB!':    { 'race.lastLapS': 90.5,   'race.bestLapS': 90.5   },
    },
  },

  lap_table: {
    fields: [
      { path: 'mock.laps.count', label: 'Laps', min: 0, max: 30, step: 1, default: 8 },
      { path: 'mock.laps.best',  label: 'Best lap (s)', min: 50, max: 150, step: 0.1, default: 91.5 },
      { path: 'mock.laps.spread', label: 'Spread (s)', min: 0,  max: 5,   step: 0.1, default: 1.2 },
    ],
    presets: {
      Few:        { 'mock.laps.count': 3, 'mock.laps.spread': 0.4 },
      Consistent: { 'mock.laps.count': 12, 'mock.laps.spread': 0.3 },
      'Tires going off': { 'mock.laps.count': 18, 'mock.laps.spread': 3.5 },
    },
    apiMocks: {
      sessionDetail: (vals: Record<string, any>) => {
        const n = Math.round(vals['mock.laps.count'] ?? 8)
        const best = vals['mock.laps.best'] ?? 91.5
        const spread = vals['mock.laps.spread'] ?? 1.2
        const lapRollups = []
        for (let i = 0; i < n; i++) {
          // Pseudo-random but stable: lap 0 = best, rest scatter
          const noise = ((i * 9301 + 49297) % 233281) / 233281
          const t = i === 0 ? best : best + noise * spread
          lapRollups.push({
            lap: i + 1,
            time_s: t,
            sectors: [t * 0.3, t * 0.4, t * 0.3],
            isBest: i === 0,
          })
        }
        return {
          id: 'sandbox-session',
          name: 'Sandbox',
          lapRollups,
          events: [],
        }
      },
    },
  },

  speed_trace: {
    fields: [
      { path: 'motion.speed_mps', label: 'Speed (m/s)', min: 0, max: 110, step: 0.5, default: 0 },
    ],
    presets: {
      Stop:     { 'motion.speed_mps': 0   },
      Cruise:   { 'motion.speed_mps': 25  },
      Highway:  { 'motion.speed_mps': 55  },
      Topspeed: { 'motion.speed_mps': 95  },
    },
    notes: 'SpeedTrace maintains an internal ring buffer from live samples. Use the Animate checkbox to sweep the speed slider and watch the trace fill in.',
  },
}

// Generic config for widgets not listed above. Just a stale toggle is useful.
export const GENERIC = {
  fields: [],
  presets: {},
  notes: "No sandbox config for this widget yet — it will render but you can't drive its data.",
}

export function getConfig(kind: string): unknown {
  return (CONFIGS as Record<string, unknown>)[kind] ?? GENERIC
}
