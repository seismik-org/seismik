import {channels, colombiaInput, toUTC, eventCard, element, safeImage} from '../events.js';
const $ = id => document.getElementById(id);
const form = $('event-form');
let revision = 0;
let editing = '';
let events = [];
let busy = false;
let previewURL = '';
function preview(value = '') {
  if (previewURL) URL.revokeObjectURL(previewURL);
  previewURL = '';
  const file = $('thumbnail').files[0];
  if (file) { previewURL = URL.createObjectURL(file); value = previewURL; }
  $('thumbnail-preview').hidden = !value;
  if (value) $('thumbnail-preview').src = value;
  else $('thumbnail-preview').removeAttribute('src');
}
function readThumbnail(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = () => reject(new Error('No se pudo leer la miniatura. Selecciónala de nuevo.'));
    reader.readAsDataURL(file);
  });
}
async function api(path, method = 'GET', body) {
  const response = await fetch('/v1/liveahora/admin/events' + path, {
    method, credentials:'same-origin', cache:'no-store', signal:AbortSignal.timeout(20000),
    headers: {'X-LiveAhora-Admin':'1', ...(body ? {'Content-Type':'application/json'} : {})},
    ...(body ? {body:JSON.stringify(body)} : {}),
  });
  if (response.status === 401) {
    $('login-panel').hidden = false; $('workspace').hidden = true;
    throw new Error('Inicia sesión en auth.seismik.org para continuar.');
  }
  if (response.status === 403) {
    $('login-panel').hidden = false;
    $('workspace').hidden = true;
    throw new Error('Esta cuenta no puede administrar LiveAhora. Usa liveahora@seismik.org.');
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'No se pudo guardar. Revisa fechas, enlace y derechos. Si persiste, recarga el cronograma.');
  }
  return response.json();
}
function message(text, failed = false) { $('admin-status').textContent = text; $('admin-status').classList.toggle('error', failed); }
function reset() {
  $('image').querySelector('option[data-uploaded]')?.remove();
  form.reset(); editing = ''; $('editor-title').textContent = 'Nuevo evento';
  preview();
  $('url').value = channels.youtube; $('delete-event').hidden = true;
  $('save-event').textContent = 'Guardar evento';
}
function edit(event) {
  reset(); editing = event.id; $('editor-title').textContent = 'Editar evento';
  if (safeImage(event.image) && event.image.startsWith('/v1/')) {
    const option = element('option', 'Miniatura subida'); option.value = event.image; option.dataset.uploaded = '1'; $('image').append(option);
  }
  for (const key of ['title','description','platform','url','image','status']) $(key).value = event[key];
  preview(safeImage(event.image) ? event.image : '');
  $('starts_at').value = colombiaInput(event.starts_at); $('ends_at').value = colombiaInput(event.ends_at);
  $('rights_confirmed').checked = event.rights_confirmed; $('delete-event').hidden = false;
  $('editor-title').scrollIntoView({behavior:'smooth', block:'center'}); $('title').focus();
}
async function load() {
  try {
    const data = await api(''); revision = data.revision; events = data.events;
    $('login-panel').hidden = true; $('workspace').hidden = false; $('account').textContent = data.email;
    $('admin-events').replaceChildren(...events.map(event => {
      const card = eventCard(event, {admin:true});
      const button = element('button','Editar evento','button'); button.type = 'button';
      button.addEventListener('click', () => { if (!busy) edit(event); });
      card.querySelector('.calendar-event-copy').append(button); return card;
    }));
    $('event-count').textContent = `${events.length} de 100 eventos · Horarios de Colombia (UTC−5)`;
    message('Cronograma actualizado.');
  } catch (error) { message(error.message, true); }
}
form.addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  if (['scheduled','live'].includes($('status').value) && !$('rights_confirmed').checked) {
    message('Confirma los derechos del evento antes de publicarlo.', true); $('rights_confirmed').focus(); return;
  }
  const data = Object.fromEntries(['title','description','platform','url','image','status'].map(key => [key, $(key).value]));
  data.starts_at = toUTC($('starts_at').value); data.ends_at = toUTC($('ends_at').value);
  data.rights_confirmed = $('rights_confirmed').checked;
  busy = true; $('save-event').disabled = true; message('Guardando…');
  try {
    const file = $('thumbnail').files[0];
    if (file && (file.size > 5 * 1024 * 1024 || !['image/jpeg','image/png','image/webp'].includes(file.type))) throw new Error('Usa una miniatura JPG, PNG o WebP de hasta 5 MB.');
    const thumbnail = file ? await readThumbnail(file) : undefined;
    await api(editing ? '/' + editing : '', editing ? 'PUT' : 'POST', {revision, event:data, thumbnail});
    reset(); await load();
  } catch (error) { message(error.message, true); }
  finally { busy = false; $('save-event').disabled = false; }
});
$('thumbnail').addEventListener('change', () => {
  const file = $('thumbnail').files[0];
  if (file && (file.size > 5 * 1024 * 1024 || !['image/jpeg','image/png','image/webp'].includes(file.type))) {
    $('thumbnail').value = ''; message('Usa una miniatura JPG, PNG o WebP de hasta 5 MB.', true);
  }
  preview(safeImage($('image').value) ? $('image').value : '');
});
$('image').addEventListener('change', () => { $('thumbnail').value = ''; preview($('image').value); });
$('platform').addEventListener('change', () => { $('url').value = channels[$('platform').value]; });
$('logout').addEventListener('click', async () => {
  if (busy) return;
  try {
    const response = await fetch('/v1/liveahora/logout', {method:'POST', credentials:'same-origin', headers:{'X-LiveAhora-Admin':'1'}, signal:AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error('No se pudo cerrar la sesión. Vuelve a intentarlo.');
    $('workspace').hidden = true; $('login-panel').hidden = false; reset();
    message('Sesión de Seismik cerrada. Puedes iniciar sesión con otra cuenta.');
  } catch (error) { message(error.message, true); }
});
$('new-event').addEventListener('click', () => { if (!busy) { reset(); $('title').focus(); } });
$('reload-events').addEventListener('click', () => { if (!busy) load(); });
$('delete-event').addEventListener('click', () => { if (!busy) $('delete-dialog').showModal(); });
$('cancel-delete').addEventListener('click', () => $('delete-dialog').close());
$('confirm-delete').addEventListener('click', async () => {
  if (!editing || busy) return;
  busy = true; $('confirm-delete').disabled = true;
  try {
    await api('/' + editing + '?revision=' + revision, 'DELETE');
    $('delete-dialog').close(); reset(); await load();
  } catch (error) { $('delete-dialog').close(); message(error.message, true); }
  finally { busy = false; $('confirm-delete').disabled = false; }
});
reset(); load();
