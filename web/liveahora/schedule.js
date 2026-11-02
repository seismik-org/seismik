import {eventCard} from './events.js';
const list = document.getElementById('event-list');
const status = document.getElementById('schedule-status');
const retry = document.getElementById('schedule-retry');
let loading = false;
async function refresh() {
  if (loading || document.hidden) return;
  loading = true;
  try {
    const response = await fetch('/v1/liveahora/events', {credentials:'omit', cache:'no-store', signal:AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error('unavailable');
    const data = await response.json();
    if (!Array.isArray(data.events)) throw new Error('invalid');
    list.replaceChildren(...data.events.map(event => eventCard(event)));
    status.textContent = data.events.length ? 'Horarios de Colombia (UTC−5). Disponibilidad sujeta a los derechos de cada evento.' : 'Aún no hay próximos eventos publicados. Encuéntranos también en nuestros canales.';
    retry.hidden = true;
  } catch {
    status.textContent = list.childElementCount ? 'No se pudo actualizar el cronograma. Los eventos visibles pueden haber cambiado.' : 'El cronograma no está disponible en este momento. Puedes consultar nuestros canales o volver a intentarlo.';
    retry.hidden = false;
  } finally { loading = false; }
}
retry.addEventListener('click', refresh);
document.addEventListener('visibilitychange', refresh);
setInterval(refresh, 60000);
refresh();
