import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync('web/email-auth.js', 'utf8').replace(/^import[\s\S]*?from "https:\/\/www\.gstatic\.com[^\n]+\n/gm, '');
async function screen(options = {}) {
  const elements = new Map();
  const calls = [];
  const node = (id) => {
    if (!elements.has(id)) elements.set(id, {
      value: '', hidden: true, checked: false, dataset: {}, listeners: {},
      addEventListener(name, fn) { this.listeners[name] = fn; },
      attributes: {}, setAttribute(name, value) { this.attributes[name] = value; },
      reportValidity() { return options.valid ?? true; },
    });
    return elements.get(id);
  };
  const user = { emailVerified: options.verified ?? true, getIdToken: async () => 'opaque-id-token' };
  const auth = { currentUser: user };
  const document = {
    getElementById: node,
    querySelector: node,
    querySelectorAll: () => [],
  };
  const context = vm.createContext({
    document, URL, URLSearchParams,
    location: { search: options.search || '', pathname: '/auth.html', assign: (url) => calls.push(['redirect', url]), replace: (url) => calls.push(['replace', url]) },
    history: { replaceState: () => calls.push(['clear-code']) },
    initializeApp: (config) => config, getAuth: () => auth,
    inMemoryPersistence: {}, setPersistence: async () => {},
    reload: async () => {}, signOut: async () => calls.push(['signout']),
    signInWithEmailAndPassword: async (...args) => {
      calls.push(['login', args[1], args[2]]);
      if (options.loginError) throw { code: options.loginError };
    },
    createUserWithEmailAndPassword: async (...args) => {
      calls.push(['register', args[1], args[2]]);
      if (options.registrationError) throw { code: options.registrationError };
      return { user };
    },
    sendEmailVerification: async () => {
      calls.push(['verify-email']);
      if (options.verificationError) throw { code: options.verificationError };
    },
    sendPasswordResetEmail: async () => {
      calls.push(['recovery']);
      if (options.recoveryError) throw { code: options.recoveryError };
    },
    applyActionCode: async () => {
      calls.push(['apply-code']);
      if (options.codeError) throw { code: 'auth/expired-action-code' };
    },
    verifyPasswordResetCode: async () => {},
    confirmPasswordReset: async () => calls.push(['confirm-reset']),
    fetch: async (url, init) => {
      if (url.endsWith('/config')) return { ok: true, json: async () => ({ enabled: true, firebase: {} }) };
      calls.push(['exchange', JSON.parse(init.body)]);
      return { ok: true, json: async () => ({ redirect: 'https://devs.seismik.org/' }) };
    },
  });
  vm.runInContext(source, context);
  async function settled() {
    for (let i = 0; i < 30; i++) await new Promise((resolve) => setImmediate(resolve));
  }
  await settled();
  function fill() {
    node('email').value = 'test@example.invalid';
    node('password').value = 'temporary-test-password';
    node('password-confirm').value = 'temporary-test-password';
  }
  fill();
  return { node, calls, fill, async click(id) { node(id).listeners.click(); await settled(); }, async submit() { node('email-form').listeners.submit({ preventDefault() {} }); await settled(); } };
}

test('registration sends credentials only to Firebase, then verification', async () => {
  const ui = await screen();
  await ui.click('email-register');
  assert.equal(ui.calls.length, 0);
  assert.match(ui.node('email-submit').textContent, /Crear cuenta/);
  assert.equal(ui.node('confirmation-fields').hidden, false);
  ui.fill();
  await ui.submit();
  assert.deepEqual(ui.calls.map(([name]) => name), ['register', 'verify-email']);
  assert.match(ui.node('email-message').textContent, /Solicitud de registro completada/);
  assert.equal(ui.node('password').value, '');
});
test('unverified users cannot exchange a token for a session', async () => {
  const ui = await screen({ verified: false });
  await ui.submit();
  assert.deepEqual(ui.calls.map(([name]) => name), ['login']);
  assert.equal(ui.node('verification-actions').hidden, false);
  assert.match(ui.node('email-message').textContent, /Verifica tu correo/);
});
test('verified login exchanges only token, flow and explicit linking intent', async () => {
  const ui = await screen();
  ui.node('link-account').checked = true;
  await ui.submit();
  assert.deepEqual(ui.calls.find(([name]) => name === 'exchange')[1], { id_token: 'opaque-id-token', flow_id: null, link: true });
  assert.deepEqual(ui.calls.slice(-2), [['signout'], ['redirect', 'https://devs.seismik.org/']]);
});
test('unknown and existing emails receive the same registration/recovery message', async () => {
  const normal = await screen();
  const existing = await screen({ registrationError: 'auth/email-already-in-use' });
  await normal.click('email-register');
  await existing.click('email-register');
  normal.fill();
  existing.fill();
  await normal.submit();
  await existing.submit();
  assert.equal(normal.node('email-message').textContent, existing.node('email-message').textContent);
  const unknown = await screen({ recoveryError: 'auth/user-not-found' });
  await normal.click('email-recover');
  await unknown.click('email-recover');
  await normal.submit();
  await unknown.submit();
  assert.equal(normal.node('email-message').textContent, unknown.node('email-message').textContent);
});

test('switching back to login submits login, never registration', async () => {
  const ui = await screen();
  await ui.click('email-register');
  await ui.click('email-login');
  ui.fill();
  await ui.submit();
  assert.equal(ui.calls[0][0], 'login');
  assert.equal(ui.calls.some(([name]) => name === 'register'), false);
  assert.equal(ui.node('confirmation-fields').hidden, true);
  assert.equal(ui.node('password').autocomplete, 'current-password');
});

test('recovery is a separate email-only form and does not login or register', async () => {
  const ui = await screen();
  await ui.click('email-recover');
  assert.equal(ui.calls.length, 0);
  assert.equal(ui.node('password').disabled, true);
  assert.equal(ui.node('password').required, false);
  await ui.submit();
  assert.deepEqual(ui.calls.map(([name]) => name), ['recovery']);
});

test('mismatched confirmation stops registration without clearing entered fields', async () => {
  const ui = await screen();
  await ui.click('email-register');
  ui.fill();
  ui.node('password-confirm').value = 'different-confirmation';
  await ui.submit();
  assert.equal(ui.calls.length, 0);
  assert.match(ui.node('email-message').textContent, /no coinciden/);
  assert.equal(ui.node('password').value, 'temporary-test-password');
});

test('invalid registration fields never call Firebase or show completion', async () => {
  const ui = await screen({ valid: false });
  await ui.click('email-register');
  ui.fill();
  await ui.submit();
  assert.equal(ui.calls.length, 0);
  assert.match(ui.node('email-message').textContent, /Revisa los campos/);
});

test('failed user creation does not claim registration or verification completion', async () => {
  const ui = await screen({ registrationError: 'auth/operation-not-allowed' });
  await ui.click('email-register');
  ui.fill();
  await ui.submit();
  assert.deepEqual(ui.calls.map(([name]) => name), ['register']);
  assert.match(ui.node('email-message').textContent, /no está disponible/);
  assert.equal(ui.node('verification-actions').hidden, true);
});

test('verification delivery failure is distinct from failed user creation', async () => {
  const ui = await screen({ verificationError: 'auth/too-many-requests' });
  await ui.click('email-register');
  ui.fill();
  await ui.submit();
  assert.deepEqual(ui.calls.map(([name]) => name), ['register', 'verify-email']);
  assert.match(ui.node('email-message').textContent, /No se pudo enviar el correo de verificación/);
  assert.equal(ui.node('verification-actions').hidden, false);
});
test('invalid credentials are neutral and password input is cleared', async () => {
  const ui = await screen({ loginError: 'auth/user-not-found' });
  await ui.submit();
  assert.doesNotMatch(ui.node('email-message').textContent, /no existe/i);
  assert.equal(ui.node('password').value, '');
  assert.equal(ui.calls.some(([name]) => name === 'exchange'), false);
});
test('verification action clears code from browser history', async () => {
  const ui = await screen({ search: '?mode=verifyEmail&oobCode=synthetic-code' });
  assert.deepEqual(ui.calls, [['apply-code'], ['clear-code']]);
  assert.match(ui.node('email-message').textContent, /confirmado|verificado/);
});
test('password reset delegates new password to Firebase and returns to login', async () => {
  const ui = await screen({ search: '?mode=resetPassword&oobCode=synthetic-code' });
  await ui.submit();
  assert.equal(ui.calls.some(([name]) => name === 'confirm-reset'), true);
  assert.equal(ui.calls.some(([name]) => name === 'exchange'), false);
  assert.deepEqual(ui.calls.slice(-2), [['signout'], ['replace', '/id']]);
});
