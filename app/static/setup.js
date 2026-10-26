// Setup page: settings, and adding / editing / deleting chores through /api.
'use strict';

const $ = id => document.getElementById(id);
let meta = null;
let chores = [];
let editing = null; // the chore being edited, or null when adding

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function option(value, label) {
  const o = el('option', null, label);
  o.value = value;
  return o;
}

async function api(path, method = 'GET', body) {
  const opts = { method, headers: { Accept: 'application/json' } };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch('/api' + path, opts);
  if (res.status === 204) return null;
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(errorText(json, res.status));
  return json;
}

function errorText(json, status) {
  if (typeof json.detail === 'string') return json.detail;
  if (Array.isArray(json.detail)) {
    return json.detail.map(d => (d.loc ? d.loc[d.loc.length - 1] + ': ' : '') + d.msg).join('; ');
  }
  return 'Request failed (' + status + ')';
}

function flash(id, text, isError = false) {
  $(id).textContent = text;
  $(id).classList.toggle('error', isError);
}

// --- Settings ------------------------------------------------------------------------------

async function loadSettings() {
  const st = await api('/settings');
  $('theme').value = st.theme;
  $('unit-id').value = st.unit_id;
}

$('settings-form').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    await api('/settings', 'PUT', { theme: $('theme').value, unit_id: $('unit-id').value.trim() });
    flash('settings-msg', 'Saved.');
  } catch (err) {
    flash('settings-msg', err.message, true);
  }
});

// --- Chores --------------------------------------------------------------------------------

async function loadChores() {
  chores = (await api('/chores')).chores;
  renderChores();
}

function renderChores() {
  $('chore-count').textContent = '(' + chores.length + ')';
  const sections = [];
  for (const z of meta.zones) {
    const items = chores.filter(c => c.zone === z.zone);
    if (!items.length) continue;
    const ul = el('ul', 'chores');
    items.forEach(c => ul.append(choreItem(c)));
    sections.push(el('h3', null, z.name), ul);
  }
  if (!sections.length) sections.push(el('p', 'msg', 'No chores yet. Add one above.'));
  $('chore-list').replaceChildren(...sections);
}

function choreItem(c) {
  const li = el('li', 'chore');
  const badge = el('span', 'badge badge-' + c.state.toLowerCase(), c.state);

  const main = el('div');
  const top = el('div', 'chore-top');
  top.append(el('span', 'code', c.code), el('span', 'name', c.name));
  const detail = 'Every ' + c.interval_days + ' d · ' + c.status + (c.snoozed ? ' · snoozed' : '');
  main.append(top, el('div', 'chore-meta', detail));

  const actions = el('div', 'actions');
  const edit = el('button', 'btn small', 'Edit');
  edit.type = 'button';
  edit.addEventListener('click', () => startEdit(c));
  const del = el('button', 'btn small danger', 'Delete');
  del.type = 'button';
  del.addEventListener('click', () => removeChore(c));
  actions.append(edit, del);

  li.append(badge, main, actions);
  return li;
}

function startEdit(c) {
  editing = c;
  $('form-title').textContent = 'Edit ' + c.code;
  $('zone').value = c.zone;
  $('category').value = String(c.category);
  $('zone').disabled = true; // the code (zone + type) is fixed once created
  $('category').disabled = true;
  $('name').value = c.name;
  $('interval').value = c.interval_days;
  $('last-done').value = c.last_done;
  $('description').value = c.description;
  $('save-chore').textContent = 'Save changes';
  $('cancel-edit').hidden = false;
  flash('chore-msg', '');
  $('chore-form').scrollIntoView({ behavior: 'smooth', block: 'center' });
  $('name').focus({ preventScroll: true });
}

function resetForm() {
  editing = null;
  $('chore-form').reset();
  $('zone').disabled = false;
  $('category').disabled = false;
  $('form-title').textContent = 'Add chore';
  $('save-chore').textContent = 'Add chore';
  $('cancel-edit').hidden = true;
}

$('cancel-edit').addEventListener('click', () => {
  resetForm();
  flash('chore-msg', '');
});

$('chore-form').addEventListener('submit', async e => {
  e.preventDefault();
  const body = {
    name: $('name').value.trim(),
    interval_days: Number($('interval').value),
    description: $('description').value.trim(),
  };
  const lastDone = $('last-done').value;
  try {
    if (editing) {
      if (lastDone && lastDone !== editing.last_done) body.last_done = lastDone;
      await api('/chores/' + encodeURIComponent(editing.code), 'PATCH', body);
      flash('chore-msg', 'Saved ' + editing.code + '.');
    } else {
      if (lastDone) body.last_done = lastDone;
      body.zone = $('zone').value;
      body.category = Number($('category').value);
      const c = await api('/chores', 'POST', body);
      flash('chore-msg', 'Added ' + c.code + '.');
    }
    resetForm();
    await loadChores();
  } catch (err) {
    flash('chore-msg', err.message, true);
  }
});

async function removeChore(c) {
  if (!confirm('Delete ' + c.code + ' ' + c.name + '? Its history is deleted too.')) return;
  try {
    await api('/chores/' + encodeURIComponent(c.code), 'DELETE');
    if (editing && editing.code === c.code) resetForm();
    flash('chore-msg', 'Deleted ' + c.code + '.');
    await loadChores();
  } catch (err) {
    flash('chore-msg', err.message, true);
  }
}

// --- Start ---------------------------------------------------------------------------------

async function init() {
  meta = await api('/meta');
  $('theme').replaceChildren(...meta.themes.map(t => option(t, t[0].toUpperCase() + t.slice(1))));
  $('zone').replaceChildren(...meta.zones.map(z => option(z.zone, z.zone + ' · ' + z.name)));
  const manual = meta.categories.filter(c => c.name !== 'Sensor'); // sensors raise their own codes
  $('category').replaceChildren(...manual.map(c => option(c.category, c.category + ' · ' + c.name)));
  await Promise.all([loadSettings(), loadChores()]);
}

init().catch(err => flash('chore-msg', 'Could not reach the unit: ' + err.message, true));
