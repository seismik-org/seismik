// Shared presentation only: all editing permissions are enforced by the API.
export const labels = {draft:'Borrador', scheduled:'Programado', live:'En directo', finished:'Finalizado', cancelled:'Cancelado'};
export const channels = {youtube:'https://youtube.com/LiveAhoraES', kick:'https://kick.com/LiveAhoraES', twitch:'https://twitch.tv/LiveAhoraES'};
const hosts = {youtube:['youtube.com','www.youtube.com','youtu.be'], kick:['kick.com','www.kick.com'], twitch:['twitch.tv','www.twitch.tv']};
export function safeEventURL(value, platform) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && hosts[platform]?.includes(url.hostname) && !url.username && !url.password && (!url.port || url.port === '443') && url.pathname.length > 1 ? url.href : null;
  } catch { return null; }
}
export function colombiaInput(value) {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'America/Bogota', year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hourCycle:'h23'}).formatToParts(new Date(value));
  const p = Object.fromEntries(parts.map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
export function toUTC(value) { return new Date(value + '-05:00').toISOString(); }
export function youtubeVideoID(value) {
  if (!safeEventURL(value, 'youtube')) return null;
  const url = new URL(value);
  const parts = url.pathname.split('/').filter(Boolean);
  let id = null;
  if (url.hostname === 'youtu.be' && parts.length === 1) id = parts[0];
  else if (url.hostname !== 'youtu.be') {
    if (url.pathname === '/watch' && url.searchParams.getAll('v').length === 1) id = url.searchParams.get('v');
    else if (['live','shorts','embed'].includes(parts[0]) && parts.length === 2) id = parts[1];
  }
  return /^[A-Za-z0-9_-]{11}$/.test(id || '') ? id : null;
}
export function safeImage(value) {
  return ['/assets/liveahora/banner.webp','/assets/liveahora/logo.webp'].includes(value) || /^\/v1\/liveahora\/images\/[a-f0-9]{24}\/[a-f0-9]{64}\.webp$/.test(value || '');
}
export function openViewer(event, opener) {
  const url = safeEventURL(event.url, event.platform);
  if (!url) return;
  const platform = {youtube:'YouTube', kick:'Kick', twitch:'Twitch'}[event.platform];
  const id = event.platform === 'youtube' ? youtubeVideoID(url) : null;
  const dialog = element('dialog', '', 'video-dialog');
  dialog.setAttribute('aria-labelledby', 'video-dialog-title');
  const title = element('h2', '¿Dónde quieres ver el video?'); title.id = 'video-dialog-title';
  const description = element('p', `Vas a salir a ${platform} para mirar el video.${id ? ' También puedes verlo aquí, sin salir de LiveAhora.' : ''}`);
  const actions = element('div', '', 'video-actions');
  const external = element('a', `Ver en ${platform} ↗`, 'button secondary');
  external.href = url; external.target = '_blank'; external.rel = 'noopener noreferrer';
  const player = element('div', '', 'video-player');
  if (id) {
    const here = element('button', 'Mirar aquí', 'button'); here.type = 'button';
    here.addEventListener('click', () => {
      const frame = element('iframe');
      frame.src = `https://www.youtube-nocookie.com/embed/${id}?rel=0`;
      frame.title = event.title || 'Video de LiveAhora';
      frame.referrerPolicy = 'strict-origin-when-cross-origin';
      frame.allow = 'encrypted-media; picture-in-picture; fullscreen'; frame.allowFullscreen = true;
      player.replaceChildren(frame); here.hidden = true;
      title.textContent = event.title || 'Video de LiveAhora'; description.hidden = true;
      frame.focus();
    });
    actions.append(here);
  }
  actions.append(external);
  const close = element('button', 'Cerrar', 'button secondary'); close.type = 'button';
  close.addEventListener('click', () => dialog.close());
  actions.append(close);
  dialog.append(title, description);
  if (id) dialog.append(element('p', 'Al elegir «Mirar aquí» se cargará el reproductor de YouTube en modo de privacidad mejorada.', 'video-note'));
  dialog.append(player, actions);
  dialog.addEventListener('close', () => { player.replaceChildren(); dialog.remove(); opener?.focus(); });
  dialog.addEventListener('click', e => { if (e.target === dialog) { const r = dialog.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close(); } });
  document.body.append(dialog); dialog.showModal();
}
export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}
export function eventCard(event, {admin = false} = {}) {
  const card = element('article', '', 'calendar-event');
  if (safeImage(event.image)) {
    const image = element('img'); image.src = event.image; image.alt = ''; image.loading = 'lazy'; image.width = 640; image.height = 360; card.append(image);
  }
  const copy = element('div', '', 'calendar-event-copy');
  copy.append(element('p', labels[event.status] || 'Evento', 'event-state'));
  copy.append(element('h3', event.title));
  const format = new Intl.DateTimeFormat('es-CO', {timeZone:'America/Bogota', dateStyle:'full', timeStyle:'short'});
  const time = element('time', format.format(new Date(event.starts_at))); time.dateTime = event.starts_at;
  copy.append(time);
  if (event.description) copy.append(element('p', event.description));
  const url = safeEventURL(event.url, event.platform);
  if (url && (admin || !['cancelled','finished'].includes(event.status))) {
    const link = element('a', 'Ver', 'button secondary');
    link.ariaLabel = `Ver ${event.title}`;
    link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.addEventListener('click', e => {
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault(); openViewer(event, link);
    });
    copy.append(link);
  }
  card.append(copy); return card;
}
