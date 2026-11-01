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
export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}
export function eventCard(event, {admin = false} = {}) {
  const card = element('article', '', 'calendar-event');
  if (['/assets/liveahora/banner.webp','/assets/liveahora/logo.webp'].includes(event.image)) {
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
    const link = element('a', `Ver en ${event.platform === 'youtube' ? 'YouTube' : event.platform === 'kick' ? 'Kick' : 'Twitch'} ↗`, 'button secondary');
    link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; copy.append(link);
  }
  card.append(copy); return card;
}
