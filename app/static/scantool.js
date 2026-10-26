// Scan-tool UI: the screen state machine from prototype/template.html, fed by /api.
'use strict';

// iOS home-screen apps with a see-through status bar report a viewport one status bar shorter
// than the screen, leaving a gap at the bottom. There the app owns the whole screen, so take the
// height from the screen itself (in portrait); everywhere else the window height is right.
function fitScreen() {
  const standalone = navigator.standalone || matchMedia('(display-mode: standalone)').matches;
  const portrait = matchMedia('(orientation: portrait)').matches;
  const h = standalone && portrait ? Math.max(screen.height, window.innerHeight) : window.innerHeight;
  document.documentElement.style.setProperty('--app-height', h + 'px');
}
fitScreen();
window.addEventListener('resize', fitScreen);
// The Pi's own 3.5" touch panel opens /?panel (deploy/homeobd-kiosk.service): the screen fills the panel.
if (new URLSearchParams(location.search).has('panel')) document.documentElement.classList.add('panel');
window.addEventListener('orientationchange', fitScreen);

const MENU = [
  ['Read codes', 'codes'],
  ['Erase codes', 'erase'],
  ['Live data', 'live'],
  ['Freeze frame', 'freezeList'],
  ['Readiness', 'ready'],
  ['Service due', 'service'],
  ['Unit info', 'info'],
  ['Help', 'manual'],
];
const BACK = {
  codes: 'menu', erase: 'menu', live: 'menu', freezeList: 'menu', ready: 'menu', service: 'menu',
  info: 'menu', manual: 'menu', guide: 'manual', detail: 'codes', confirm: 'detail', freeze: 'freezeList',
};
const DETAIL_ROWS = ['Mark done', 'Help'];
// Generic illustrations shown in a plant chore's Help, matched by the chore's name.
const PLANT_PICTURES = [
  [/celosia/i, 'celosia', 'Plumed celosia'],
  [/mint/i, 'mint', 'Mint'],
  [/money plant|pilea/i, 'pilea', 'Chinese money plant'],
  [/umbrella|schefflera/i, 'schefflera', 'Umbrella plant'],
  [/palm/i, 'palm', 'Palm'],
  [/bird of paradise/i, 'bird-of-paradise', 'Bird of paradise'],
];

function plantPicture(c) {
  const match = PLANT_PICTURES.find(([re]) => re.test(c.name));
  return match ? [{ img: '/static/pictures/' + match[1] + '.svg', alt: match[2] }] : [];
}
// Guide topics listed at the top of Help, before the chores. One string per screen line.
const GUIDE = [
  { title: 'How to use it', lines: [
    'DAY TO DAY',
    '1. A notification tells you when chores come up.',
    '2. Open APT-OBD and tap Read codes.',
    '3. Tap a code, then Help to see how to do it and what done looks like.',
    '4. Do the chore, then Mark done and YES. The code clears and its timer restarts.',
    '5. Can\'t get to it today? Erase codes hides due chores for 24 h.',
    ' ',
    'NOW AND THEN',
    'Live data: your health % and streak.',
    'Service due: maintenance coming up.',
    'Setup: add or edit chores, how often, how long they take, and notifications.',
  ] },
  { title: 'Add & edit chores', lines: [
    'ADD A CHORE',
    { img: '/static/pictures/setup-open.svg', alt: 'Tap the Setup gear at the top right' },
    '1. Tap Setup (the gear) at the top right.',
    { img: '/static/pictures/setup-add.svg', alt: 'The Add chore form with numbered steps' },
    '1. Pick the zone and type, and name the chore.',
    '2. Set how often (days) and when you last did it. Blank means today.',
    '3. Set how long it takes. 1 h or more means weekend reminders.',
    '4. Optional: steps under How to do it (one per line) and Done when.',
    '5. Tap Add chore. It gets the next free code, like K0005.',
    '\u00a0',
    'EDIT OR DELETE',
    { img: '/static/pictures/setup-edit.svg', alt: 'The chore list with Edit and Delete buttons' },
    '1. Find the chore under Chores and tap Edit.',
    '2. Change anything except zone and type (they make up the code), then Save changes.',
    '3. Delete removes the chore and its history.',
    '\u00a0',
    'Tap ‹ Scanner at the top to come back.',
  ] },
  { title: 'Codes & states', lines: [
    'Every chore is a code like K0001.',
    ' ',
    'LETTER = ZONE',
    'K Kitchen, B Bath, L Living, R Bedroom, U Utility, G Whole apt.',
    ' ',
    'FIRST DIGIT = TYPE',
    '0 routine, 1 deep clean, 2 maintenance.',
    ' ',
    'STATES',
    'PEND: due today or soon.',
    'CONF: overdue.',
    'PERM: overdue by a full interval (at least 7 d). Erase codes can\'t hide it.',
    'Chores that aren\'t due don\'t show in Read codes.',
  ] },
  { title: 'CHK APT lamp', lines: [
    'The amber CHK APT light in the title bar, like a check-engine light.',
    ' ',
    'On: at least one chore is overdue (CONF or PERM).',
    'Off: nothing overdue, or everything overdue is snoozed with Erase codes.',
    'PERM codes keep it on until they are done.',
  ] },
  { title: 'Notifications', lines: [
    'Quick chores, every 1-2 days and under 1 h: 8 pm on the day they are due.',
    'Other chores under 1 h: 8 am, and again at 6 pm on weekdays if still open.',
    'Chores of 1 h or more: weekends only, 8 am and 6 pm.',
    'A chore can also have a fixed time every day: set Notify at in Setup. Unload the dishwasher is 8 am, Load is 8 pm.',
    ' ',
    'They repeat in their slot each day until you mark the chore done.',
    'Erased (snoozed) chores stay quiet for 24 h.',
    'Turn on, test or off in Setup. Change how long a chore takes there too.',
  ] },
  { title: 'Read codes', lines: [
    'Every chore that is due or overdue, worst first: PERM, then CONF, then PEND.',
    ' ',
    'Tap a code for its zone, state, interval, time it takes and last done date.',
    'Help: steps and what done looks like.',
    'Mark done: clears the code and restarts its timer.',
  ] },
  { title: 'Erase codes', lines: [
    'Snoozes every due code except PERM for 24 h.',
    ' ',
    'Snoozed codes leave Read codes, stop notifying and turn the lamp off unless a PERM code is left.',
    ' ',
    'Nothing is marked done: health does not change and the codes come back after 24 h.',
  ] },
  { title: 'Live data', lines: [
    'Health: share of all chores that are not overdue.',
    'Overdue / Pending codes: how many are CONF+PERM / PEND.',
    'Check apt lamp: ON or OFF.',
    'Streak: days in a row that ended with nothing overdue. Best streak is your record.',
    'Next service: the soonest maintenance chore.',
    'Tasks tracked: how many chores there are.',
  ] },
  { title: 'Freeze frame', lines: [
    'Like a car\'s freeze frame: a snapshot taken when a code went overdue.',
    ' ',
    'Set on: when it went overdue.',
    'Health at set: your health % at that moment.',
    'Streak at set: the streak it broke.',
    ' ',
    'Only overdue codes have one; pending codes say "No freeze frame". It clears when you mark the chore done.',
  ] },
  { title: 'Readiness', lines: [
    'A check per zone, like a car\'s emissions readiness.',
    ' ',
    'RDY: nothing in that zone is overdue or snoozed.',
    'INC (incomplete): something there is overdue or snoozed.',
    ' ',
    'Aim for 6 of 6 zones ready.',
  ] },
  { title: 'Service due', lines: [
    'Maintenance chores (codes with first digit 2): filters, updates, backups, replacements.',
    ' ',
    'Sorted by days left. OVR means overdue by that many days.',
  ] },
  { title: 'Unit info', lines: [
    'About this scanner: its unit ID, software version, the Raspberry Pi it runs on, and how many zones and chores it tracks.',
    'Change the unit ID and screen colours in Setup.',
  ] },
];
const FULL = { PERM: 'Permanent', CONF: 'Confirmed', PEND: 'Pending' };
const THEMES = ['classic', 'amber', 'green'];
const BOOT_TICK_MS = 140;
const REFRESH_MS = 60000;

// UI state. `idx` holds the cursor for each list screen.
const s = {
  screen: 'boot', progress: 0, booted: false, bootError: false, skip: false,
  idx: { menu: 0, codes: 0, freezeList: 0, detail: 0, manual: 0 },
  sel: null, msg: null, busy: false,
  helpRet: 'detail', // where EXIT goes from a chore's help: its code detail or the Help list
};
// Last data read from the unit.
const data = {
  codes: [], chores: [], lamp: false, theme: 'classic',
  unit: null, live: null, ready: null, service: null, freeze: null,
};

async function api(path, method = 'GET') {
  const res = await fetch('/api' + path, { method, headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(method + ' ' + path + ': ' + res.status);
  return res.json();
}

async function loadCodes() {
  const r = await api('/codes');
  data.codes = r.codes;
  data.lamp = r.lamp;
  for (const k of ['codes', 'freezeList']) {
    s.idx[k] = Math.min(s.idx[k], Math.max(0, data.codes.length - 1));
  }
}

const LOADERS = {
  menu: loadCodes,
  codes: loadCodes,
  erase: loadCodes,
  freezeList: loadCodes,
  live: async () => { data.live = await api('/live'); },
  ready: async () => { data.ready = await api('/readiness'); },
  service: async () => { data.service = await api('/service'); },
  info: async () => { data.unit = await api('/unit'); },
  manual: async () => { data.chores = (await api('/chores')).chores; },
  freeze: async () => {
    data.freeze = null; // never show the previous code's frame
    data.freeze = await api('/codes/' + encodeURIComponent(s.sel) + '/freeze');
  },
};

// --- Navigation ----------------------------------------------------------------------------

async function go(screen) {
  s.screen = screen;
  render();
  const load = LOADERS[screen];
  if (!load) return;
  try {
    await load();
  } catch (e) {
    linkLost();
    return;
  }
  if (s.screen === screen) render();
}

function showMsg(title, lines, ret) {
  s.msg = { title, lines, ret };
  s.screen = 'msg';
  render();
}

function linkLost() {
  showMsg('Link lost', ['No reply from unit.', 'Check the Pi is on.'], 'menu');
}

async function busy(fn) {
  s.busy = true;
  try {
    await fn();
  } catch (e) {
    linkLost();
  } finally {
    s.busy = false;
  }
}

function boot() {
  Object.assign(s, { screen: 'boot', progress: 0, booted: false, bootError: false, skip: false });
  render();
  const timer = setInterval(() => {
    s.progress = Math.min(100, s.progress + 10);
    if (s.progress >= 100) clearInterval(timer);
    finishBoot();
  }, BOOT_TICK_MS);
  Promise.all([api('/settings'), api('/unit'), loadCodes()])
    .then(([settings, unit]) => {
      data.theme = THEMES.includes(settings.theme) ? settings.theme : 'classic';
      data.unit = unit;
      s.booted = true;
      finishBoot();
    })
    .catch(() => {
      clearInterval(timer);
      s.bootError = true;
      render();
    });
}

function finishBoot() {
  if (s.screen !== 'boot') return;
  if (s.booted && (s.progress >= 100 || s.skip)) s.screen = 'menu';
  render();
}

function selected() {
  return data.codes.find(c => c.code === s.sel);
}

// Any chore, due or not: the Help list reads all chores, code detail only the active ones.
function chore(code) {
  return data.chores.find(c => c.code === code) || data.codes.find(c => c.code === code);
}

function erasable() {
  return data.codes.filter(c => c.state !== 'PERM');
}

function move(d) {
  if (!(s.screen in s.idx)) return;
  const n = { menu: MENU.length, detail: DETAIL_ROWS.length, manual: GUIDE.length + data.chores.length }[s.screen]
    ?? data.codes.length;
  if (!n) return;
  s.idx[s.screen] = (s.idx[s.screen] + d + n) % n;
  render();
}

function enter() {
  if (s.busy) return;
  switch (s.screen) {
    case 'boot':
      if (s.bootError) return boot();
      s.skip = true;
      return finishBoot();
    case 'menu': {
      const target = MENU[s.idx.menu][1];
      if (target in s.idx) s.idx[target] = 0;
      return go(target);
    }
    case 'codes':
    case 'freezeList': {
      const c = data.codes[s.idx[s.screen]];
      if (!c) return;
      s.sel = c.code;
      s.idx.detail = 0;
      return go(s.screen === 'codes' ? 'detail' : 'freeze');
    }
    case 'detail':
      if (!selected()) return go('codes');
      s.helpRet = 'detail';
      return go(s.idx.detail === 0 ? 'confirm' : 'help');
    case 'manual': {
      if (s.idx.manual < GUIDE.length) {
        s.guide = s.idx.manual;
        return go('guide');
      }
      const c = data.chores[s.idx.manual - GUIDE.length];
      if (!c) return;
      s.sel = c.code;
      s.helpRet = 'manual';
      return go('help');
    }
    case 'help':
      return go(s.helpRet);
    case 'confirm':
      return busy(markDone);
    case 'msg':
      return go(s.msg.ret);
    case 'erase':
      return erasable().length ? busy(eraseCodes) : go('menu');
  }
}

function exit() {
  if (s.busy) return;
  if (s.screen === 'msg') return go(s.msg.ret);
  if (s.screen === 'help') return go(s.helpRet);
  if (s.screen === 'boot') {
    s.skip = true;
    return finishBoot();
  }
  if (BACK[s.screen]) go(BACK[s.screen]);
}

function pick(i) {
  if (!(s.screen in s.idx)) return;
  s.idx[s.screen] = i;
  enter();
}

async function markDone() {
  const code = s.sel;
  const r = await api('/codes/' + encodeURIComponent(code) + '/done', 'POST');
  await loadCodes();
  s.idx.codes = 0;
  showMsg('Code cleared', [code + ' cleared.', 'Health now ' + r.health + ' %.'], 'codes');
}

async function eraseCodes() {
  const r = await api('/codes/erase', 'POST');
  await loadCodes();
  const n = r.erased.length;
  const perm = r.permanent_remaining;
  const lines = [n + (n === 1 ? ' code' : ' codes') + ' erased.'];
  if (perm) lines.push(perm === 1 ? '1 permanent code keeps' : perm + ' permanent codes keep', 'CHECK APT on.');
  else lines.push('CHECK APT off for 24 h.');
  lines.push('Health is unchanged:', 'the chores still wait.');
  showMsg('Codes erased', lines, 'menu');
}

// Re-read the current screen's data now and then, and when the phone comes back to the tab.
async function refresh() {
  const screen = s.screen;
  if (s.busy || document.hidden || screen === 'freeze' || !(screen in LOADERS)) return;
  try {
    await loadCodes();
    if (LOADERS[screen] !== loadCodes) await LOADERS[screen]();
  } catch (e) {
    return; // keep showing the last data; a key press will report the lost link
  }
  if (s.screen === screen && !s.busy) render();
}

// --- Rendering -----------------------------------------------------------------------------

function fmtDate(iso) {
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function days(n) {
  return n + ' d';
}

// "Next due Thu, Oct 29 (in 3 d)", "Due today" or "Was due Sat, Oct 24 (2 d ago)".
function dueText(c) {
  const when = new Date(c.due + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  if (c.days_left > 0) return 'Next due ' + when + ' (in ' + days(c.days_left) + ')';
  if (c.days_left === 0) return 'Due today';
  return 'Was due ' + when + ' (' + days(-c.days_left) + ' ago)';
}

const SPACER = ' '; // an empty screen line that still takes up height

function textLines(text) {
  return (text || '').split('\n').map(t => t.trim()).filter(Boolean);
}

function view() {
  // keys: footer action buttons [label, action]. Back lives in the title bar (see render).
  const v = { title: '', lines: [], pairs: [], rows: [], foot: '', keys: [], bar: null };
  const kv = (k, val) => v.pairs.push([k, String(val)]);
  const reading = () => { v.lines = ['Reading...']; };
  const codeRows = key => data.codes.map((c, i) => ({
    label: c.code + ' ' + c.name, tag: c.state, sel: i === s.idx[key], i,
  }));

  switch (s.screen) {
    case 'boot':
      v.title = 'APT-OBD';
      if (s.bootError) {
        v.lines = ['Link failed.', 'Check the Pi is on.'];
        v.keys = [['RETRY', 'enter']];
        break;
      }
      v.lines = [
        'Software ' + (data.unit ? data.unit.software : '...'),
        'Linking to unit ' + (data.unit ? data.unit.unit_id : '...'),
        'Please wait  ' + s.progress + ' %',
      ];
      v.bar = s.progress;
      v.keys = [['SKIP', 'enter']];
      break;
    case 'menu':
      v.title = 'Diagnostic menu';
      v.rows = MENU.map(([name], i) => ({
        label: name, tag: i === 0 && data.codes.length ? String(data.codes.length) : '', sel: i === s.idx.menu, i,
      }));
      v.foot = 'Tap to open';
      break;
    case 'codes':
      v.title = 'Read codes';
      v.foot = 'Tap a code';
      if (!data.codes.length) v.lines = ['No codes found.', 'Apartment is healthy.'];
      else {
        v.rows = codeRows('codes');
      }
      break;
    case 'detail': {
      const c = selected();
      v.title = s.sel;
      if (!c) {
        v.lines = ['Code no longer active.'];
        break;
      }
      v.lines = [c.name];
      kv('Zone', c.zone_name);
      kv('State', FULL[c.state]);
      kv('Status', c.status);
      kv('Interval', days(c.interval_days));
      kv('Takes', 'about ' + c.minutes + ' min');
      kv('Last done', fmtDate(c.last_done));
      v.rows = DETAIL_ROWS.map((label, i) => ({ label, tag: '', sel: i === s.idx.detail, i }));
      break;
    }
    case 'manual':
      v.title = 'Help';
      v.foot = 'Tap a chore';
      if (!data.chores.length) v.lines = ['Reading...'];
      else {
        v.rows = [
          ...GUIDE.map((g, i) => ({ label: g.title, tag: 'GUIDE', sel: i === s.idx.manual, i })),
          ...data.chores.map((c, j) => {
            const i = GUIDE.length + j;
            return { label: c.code + ' ' + c.name, tag: days(c.interval_days), sel: i === s.idx.manual, i };
          }),
        ];
      }
      break;
    case 'guide': {
      const g = GUIDE[s.guide] || GUIDE[0];
      v.title = g.title;
      v.lines = g.lines;
      break;
    }
    case 'help': {
      const c = chore(s.sel);
      v.title = 'Help ' + s.sel;
      if (!c || !(c.how_to || c.done_when)) {
        v.lines = ['No help yet.', 'Add it on the Setup page.'];
        break;
      }
      v.lines = [c.name, ...plantPicture(c), dueText(c), 'Takes about ' + c.minutes + ' min', SPACER, ...textLines(c.how_to)];
      if (c.done_when) {
        if (c.how_to) v.lines.push(SPACER);
        v.lines.push('DONE WHEN', ...textLines(c.done_when));
      }
      break;
    }
    case 'confirm': {
      const c = selected();
      v.title = 'Mark done';
      v.lines = c && c.done_when
        ? ['Mark ' + s.sel + ' done?', SPACER, 'Done when:', ...textLines(c.done_when)]
        : ['Mark ' + s.sel + ' done?', 'Only if the chore', 'is really finished.'];
      v.keys = [['YES', 'enter'], ['NO', 'exit']];
      break;
    }
    case 'msg':
      v.title = s.msg.title;
      v.lines = s.msg.lines;
      v.keys = [['CONTINUE', 'enter']];
      break;
    case 'erase': {
      v.title = 'Erase codes';
      const can = erasable().length;
      if (!can) {
        v.lines = ['No codes to erase.'];
        if (data.codes.length) v.lines.push('Permanent codes clear', 'only when the chore', 'is done.');
      } else {
        v.lines = [
          'Erase ' + can + (can === 1 ? ' code?' : ' codes?'),
          'Erased codes return', 'in 24 h if the chores', 'are not done.', 'Permanent codes stay.',
        ];
        v.keys = [['ERASE', 'enter'], ['CANCEL', 'exit']];
      }
      break;
    }
    case 'live': {
      v.title = 'Live data';
      const l = data.live;
      if (!l) { reading(); break; }
      kv('Health', l.health + ' %');
      kv('Overdue codes', l.overdue);
      kv('Pending codes', l.pending);
      kv('Check apt lamp', l.lamp ? 'ON' : 'OFF');
      kv('Streak', days(l.streak));
      kv('Best streak', days(l.best_streak));
      kv('Next service', l.next_service ? l.next_service.name + ' ' + days(l.next_service.days_left) : 'None');
      kv('Tasks tracked', l.tasks);
      break;
    }
    case 'freezeList':
      v.title = 'Freeze frame';
      v.foot = 'Tap a code';
      if (!data.codes.length) v.lines = ['No frames stored.'];
      else {
        v.rows = codeRows('freezeList');
      }
      break;
    case 'freeze': {
      v.title = 'Frame ' + s.sel;
      const f = data.freeze;
      if (!f) { reading(); break; }
      const c = f.code;
      if (c.state === 'PEND') {
        v.lines = ['No freeze frame.', 'Code is still pending.'];
        break;
      }
      if (!f.frame) {
        v.lines = ['No freeze frame.'];
        break;
      }
      v.lines = [c.name];
      kv('Set on', fmtDate(f.frame.set_on));
      kv('Health at set', f.frame.health_at_set + ' %');
      kv('Streak at set', days(f.frame.streak_at_set));
      kv('Last done', fmtDate(c.last_done));
      kv('Interval', days(c.interval_days));
      break;
    }
    case 'ready': {
      v.title = 'Readiness';
      const r = data.ready;
      if (!r) { reading(); break; }
      v.lines = [r.ready + ' of ' + r.total + ' zones ready'];
      r.zones.forEach(z => kv(z.name, z.status));
      break;
    }
    case 'service': {
      v.title = 'Service due';
      const sv = data.service;
      if (!sv) { reading(); break; }
      sv.items.forEach(x => kv(x.code + ' ' + x.name, x.days_left < 0 ? 'OVR ' + days(-x.days_left) : days(x.days_left)));
      break;
    }
    case 'info': {
      v.title = 'Unit info';
      const u = data.unit;
      if (!u) { reading(); break; }
      kv('Unit ID', u.unit_id);
      kv('Software', u.software);
      kv('ECU', u.ecu);
      kv('Interface', u.interface);
      kv('Zones', u.zones);
      kv('Tasks', u.tasks);
      break;
    }
  }
  return v;
}

const $ = id => document.getElementById(id);

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function render() {
  const v = view();
  $('screen').className = 'screen theme-' + data.theme;
  $('title').textContent = v.title;
  $('lamp').hidden = !data.lamp;
  $('back').hidden = !(BACK[s.screen] || s.screen === 'help');
  if (v.keys.length) {
    $('foot').replaceChildren(...v.keys.map(([label, action]) => {
      const b = el('button', 'softkey', label);
      b.type = 'button';
      b.addEventListener('click', action === 'enter' ? enter : exit);
      return b;
    }));
  } else {
    $('foot').replaceChildren();
    $('foot').textContent = v.foot;
  }

  const nodes = v.lines.map(t => {
    if (typeof t === 'string') return el('div', 'line', t);
    const img = el('img', 'pic');
    img.src = t.img;
    img.alt = t.alt;
    return img;
  });
  if (v.bar != null) {
    const bar = el('div', 'bar');
    const fill = el('div');
    fill.style.width = v.bar + '%';
    bar.append(fill);
    nodes.push(bar);
  }
  for (const [k, val] of v.pairs) {
    const p = el('div', 'pair');
    p.append(el('span', 'k clip', k), el('span', 'v clip', val));
    nodes.push(p);
  }
  for (const r of v.rows) {
    const b = el('button', 'row' + (r.sel ? ' sel' : ''));
    b.type = 'button';
    b.append(el('span', 'clip', r.label), el('span', 'nowrap', r.tag));
    b.addEventListener('click', () => pick(r.i));
    nodes.push(b);
  }
  const body = $('body');
  body.replaceChildren(...nodes);
  const sel = body.querySelector('.row.sel');
  if (sel) sel.scrollIntoView({ block: 'nearest' });
}

// --- Wiring --------------------------------------------------------------------------------


$('back').addEventListener('click', exit);

document.addEventListener('keydown', e => {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  const fn = { ArrowUp: () => move(-1), ArrowDown: () => move(1), Enter: enter, Escape: exit, Backspace: exit }[e.key];
  if (!fn) return;
  e.preventDefault(); // also stops Enter from clicking a focused button a second time
  fn();
});
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
setInterval(refresh, REFRESH_MS);

boot();

// Offline app shell for the home-screen app; browsers only allow this over HTTPS.
if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}
