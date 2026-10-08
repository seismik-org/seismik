"use strict";
// Secrets/codes stay in this page's memory; never in URL, storage or telemetry.
let actionRequest = null;
let enrollmentTimer = null;
let mfaGeneration = 0;
function clearEnrollment() {
  clearTimeout(enrollmentTimer);
  enrollmentTimer = null;
  $('#mfa-secret').textContent = '';
  $('#mfa-qr').width = 0;
  $('#mfa-qr').height = 0;
  $('#mfa-manual').open = false;
  $('#mfa-setup').hidden = true;
}
function renderMfaQr(uri) {
  const qr = qrcodegen.QrCode.encodeText(uri, qrcodegen.QrCode.Ecc.MEDIUM);
  const canvas = $('#mfa-qr');
  const scale = 6, border = 4;
  canvas.width = canvas.height = (qr.size + border * 2) * scale;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('No se pudo mostrar el QR. Usa la clave manual.');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#000000';
  for (let y = 0; y < qr.size; y++) for (let x = 0; x < qr.size; x++) {
    if (qr.getModule(x, y)) ctx.fillRect((x + border) * scale, (y + border) * scale, scale, scale);
  }
}
function clearMfa() {
  mfaGeneration++;
  clearEnrollment();
  for (const id of ['#mfa-code', '#action-code']) $(id).value = '';
  $('#mfa-recovery').textContent = '';
  $('#mfa-setup').hidden = true;
  $('#mfa-backup').hidden = true;
  $('#mfa').hidden = true;
  if (actionRequest) { actionRequest.resolve(null); actionRequest = null; }
  if ($('#action-mfa').open) $('#action-mfa').close();
}
async function adminAuthenticate() {
  const params = new URLSearchParams(location.search);
  const code = params.get('admin_code');
  if (code) {
    // Remove the single-use handoff before any subsequent navigation.
    history.replaceState(null, '', location.pathname);
    await api('/v1/admin/auth/exchange', {method:'POST', body:JSON.stringify({code})});
  }
  const status = await api('/v1/admin/auth/status');
  showUser(status.email);
  if (status.verified) return true;
  $('#app').hidden = true;
  $('#gate').hidden = true;
  $('#mfa').hidden = false;
  $('#mfa-title').textContent = status.enrolled ? 'Verifica tu autenticador' : 'Configura tu autenticador';
  $('#mfa-description').textContent = status.enrolled
    ? 'Introduce un código nuevo de tu aplicación. Si perdiste acceso, puedes usar un código de recuperación una sola vez para entrar.'
    : 'Admin requiere un segundo factor. Usa Google Authenticator, Microsoft Authenticator, Aegis, 1Password u otra aplicación compatible con TOTP.';
  $('#mfa-enroll').hidden = status.enrolled;
  $('#mfa-form').hidden = !status.enrolled;
  return false;
}
$('#mfa-enroll').addEventListener('click', async () => {
  const generation = mfaGeneration;
  $('#mfa-enroll').disabled = true;
  try {
    const data = await api('/v1/admin/auth/enroll', {method:'POST'});
    if (generation !== mfaGeneration) return;
    clearEnrollment();
    $('#mfa-code').value = '';
    $('#mfa-secret').textContent = data.secret;
    $('#mfa-setup').hidden = false;
    $('#mfa-form').hidden = false;
    $('#mfa-enroll').hidden = true;
    $('#mfa-message').textContent = 'Este QR y su clave expiran en cinco minutos. Confirma con el código de seis dígitos de tu aplicación.';
    enrollmentTimer = setTimeout(() => {
      clearEnrollment();
      $('#mfa-code').value = '';
      $('#mfa-form').hidden = true;
      $('#mfa-message').textContent = 'La configuración expiró. Vuelve a iniciar sesión para generar otro QR.';
    }, 300000);
    try { renderMfaQr(data.uri); }
    catch { $('#mfa-manual').open = true; $('#mfa-message').textContent = 'No se pudo mostrar el QR. Puedes usar la clave manual y confirmar el código.'; }
  } catch (error) { $('#mfa-message').textContent = error.message; }
  finally { $('#mfa-enroll').disabled = false; }
});
$('#mfa-form').addEventListener('submit', async event => {
  event.preventDefault();
  const generation = mfaGeneration;
  $('#mfa-submit').disabled = true;
  try {
    const data = await api('/v1/admin/auth/verify', {method:'POST', body:JSON.stringify({code:$('#mfa-code').value})});
    if (generation !== mfaGeneration) return;
    $('#mfa-code').value = '';
    clearEnrollment();
    if (data.recovery_codes.length) {
      $('#mfa-recovery').textContent = data.recovery_codes.join('\n');
      $('#mfa-form').hidden = true;
      $('#mfa-enroll').hidden = true;
      $('#mfa-backup').hidden = false;
      $('#mfa-message').textContent = 'MFA activado. Guarda estos códigos en tu gestor de contraseñas o en un lugar seguro. Se muestran una sola vez; cada uno permite entrar una vez, pero no autoriza cambios críticos.';
    } else { clearMfa(); await start(); }
  } catch (error) { $('#mfa-message').textContent = error.message; }
  finally { $('#mfa-code').value = ''; $('#mfa-submit').disabled = false; }
});
window.addEventListener('pagehide', clearMfa);
$('#mfa-continue').addEventListener('click', () => { clearMfa(); start(); });
function approveAction(action, label) {
  if (actionRequest) return Promise.resolve(null);
  $('#action-description').textContent = label;
  $('#action-code').value = '';
  $('#action-message').textContent = 'Introduce un código nuevo del autenticador. Esta autorización sirve una sola vez para este cambio y expira en dos minutos.';
  $('#action-mfa').showModal();
  $('#action-code').focus();
  return new Promise(resolve => { actionRequest = {action, resolve}; });
}
function cancelAction() {
  if (actionRequest) { actionRequest.resolve(null); actionRequest = null; }
  $('#action-code').value = '';
  $('#action-mfa').close();
}
$('#action-cancel').addEventListener('click', cancelAction);
$('#action-mfa').addEventListener('cancel', event => { event.preventDefault(); cancelAction(); });
$('#action-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (!actionRequest) return;
  const current = actionRequest;
  $('#action-submit').disabled = true;
  try {
    const data = await api('/v1/admin/auth/verify', {method:'POST', body:JSON.stringify({code:$('#action-code').value, action:current.action})});
    if (actionRequest !== current) return;
    actionRequest = null;
    $('#action-mfa').close();
    current.resolve(data.approval);
  } catch (error) { $('#action-message').textContent = error.message; }
  finally { $('#action-code').value = ''; $('#action-submit').disabled = false; }
});
