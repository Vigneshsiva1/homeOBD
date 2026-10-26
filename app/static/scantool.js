// Scan-tool UI: the screen state machine from prototype/template.html, fed by /api.
'use strict';

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
  info: 'menu', manual: 'menu', detail: 'codes', confirm: 'detail', freeze: 'freezeList',
};
const DETAIL_ROWS = ['Mark done', 'Help'];
const FULL = { PERM: 'Permanent', CONF: 'Confirmed', PEND: 'Pending' };
const THEMES = ['classic', 'amber', 'green'];
const MOVE_FOOT = '▲▼ move  ENTER view  EXIT back';
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
  const n = { menu: MENU.length, detail: DETAIL_ROWS.length, manual: data.chores.length }[s.screen]
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
      const c = data.chores[s.idx.manual];
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

const SPACER = ' '; // an empty screen line that still takes up height

function textLines(text) {
  return (text || '').split('\n').map(t => t.trim()).filter(Boolean);
}

function view() {
  const v = { title: '', lines: [], pairs: [], rows: [], foot: 'EXIT back', bar: null };
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
        v.foot = 'ENTER retry';
        break;
      }
      v.lines = [
        'Software ' + (data.unit ? data.unit.software : '...'),
        'Linking to unit ' + (data.unit ? data.unit.unit_id : '...'),
        'Please wait  ' + s.progress + ' %',
      ];
      v.bar = s.progress;
      v.foot = 'ENTER skip';
      break;
    case 'menu':
      v.title = 'Diagnostic menu';
      v.rows = MENU.map(([name], i) => ({
        label: name, tag: i === 0 && data.codes.length ? String(data.codes.length) : '', sel: i === s.idx.menu, i,
      }));
      v.foot = '▲▼ move  ENTER open';
      break;
    case 'codes':
      v.title = 'Read codes';
      if (!data.codes.length) v.lines = ['No codes found.', 'Apartment is healthy.'];
      else {
        v.rows = codeRows('codes');
        v.foot = MOVE_FOOT;
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
      kv('Last done', fmtDate(c.last_done));
      v.rows = DETAIL_ROWS.map((label, i) => ({ label, tag: '', sel: i === s.idx.detail, i }));
      v.foot = '▲▼ move  ENTER select  EXIT back';
      break;
    }
    case 'manual':
      v.title = 'Help';
      if (!data.chores.length) v.lines = ['Reading...'];
      else {
        v.rows = data.chores.map((c, i) => ({
          label: c.code + ' ' + c.name, tag: days(c.interval_days), sel: i === s.idx.manual, i,
        }));
        v.foot = MOVE_FOOT;
      }
      break;
    case 'help': {
      const c = chore(s.sel);
      v.title = 'Help ' + s.sel;
      if (!c || !(c.how_to || c.done_when)) {
        v.lines = ['No help yet.', 'Add it on the Setup page.'];
        break;
      }
      v.lines = [c.name, SPACER, ...textLines(c.how_to)];
      if (c.done_when) {
        if (c.how_to) v.lines.push(SPACER);
        v.lines.push('DONE WHEN', ...textLines(c.done_when));
      }
      v.foot = 'ENTER or EXIT back';
      break;
    }
    case 'confirm': {
      const c = selected();
      v.title = 'Mark done';
      v.lines = c && c.done_when
        ? ['Mark ' + s.sel + ' done?', SPACER, 'Done when:', ...textLines(c.done_when)]
        : ['Mark ' + s.sel + ' done?', 'Only if the chore', 'is really finished.'];
      v.foot = 'ENTER yes  EXIT no';
      break;
    }
    case 'msg':
      v.title = s.msg.title;
      v.lines = s.msg.lines;
      v.foot = 'ENTER continue';
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
        v.foot = 'ENTER erase  EXIT cancel';
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
      if (!data.codes.length) v.lines = ['No frames stored.'];
      else {
        v.rows = codeRows('freezeList');
        v.foot = MOVE_FOOT;
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
  $('foot').textContent = v.foot;

  const nodes = v.lines.map(t => el('div', 'line', t));
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

$('key-up').addEventListener('click', () => move(-1));
$('key-down').addEventListener('click', () => move(1));
$('key-enter').addEventListener('click', enter);
$('key-exit').addEventListener('click', exit);

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
