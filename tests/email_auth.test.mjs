import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync('web/email-auth.js', 'utf8').replace(/^import[\s\S]*?from "https:\/\/www\.gstatic\.com[^\n]+\n/gm, '');
async function screen(options = {}) {
  const elements = new Map();
  const calls = [];
  const mail = [];
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
      if (url.endsWith('/account/center')) {
        if (options.center === null) return { ok: false, status: 401, json: async () => ({ detail: 'Inicia sesión' }) };
        return { ok: true, json: async () => options.center || {
          name: 'Ana', email: 'ana@example.test', current_method: 'google', recent_login: true,
          methods: [{ id: 'google', primary: true, linked: true }, { id: 'email', primary: false, linked: false }],
        } };
      }
      if (url.endsWith('/verify-request') || url.endsWith('/reset-request')) {
        mail.push([url.split('/').pop(), JSON.parse(init.body)]);
        return { ok: options.seismikMail === true, json: async () => ({ accepted: true }) };
      }
      calls.push(['exchange', JSON.parse(init.body)]);
      if (options.exchangeError) return { ok: false, json: async () => ({ detail: options.exchangeError }) };
      return { ok: true, json: async () => ({ redirect: options.redirect || 'https://devs.seismik.org/' }) };
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
  return { node, calls, mail, fill, async click(id) { node(id).listeners.click(); await settled(); }, async submit() { node('email-form').listeners.submit({ preventDefault() {} }); await settled(); } };
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
test('a login that started in Waves may return to Waves, and only to Waves', async () => {
  const waves = await screen({ redirect: 'https://waves.seismik.org/' });
  await waves.submit();
  assert.deepEqual(waves.calls.slice(-2), [['signout'], ['redirect', 'https://waves.seismik.org/']]);
  for (const redirect of ['https://waves.seismik.org.evil.example/', 'https://evil.example/', 'http://waves.seismik.org/']) {
    const rejected = await screen({ redirect });
    await rejected.submit();
    assert.equal(rejected.calls.some(([name]) => name === 'redirect'), false, redirect);
  }
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

test('verification and recovery go through Seismik when its mail is available, without using Firebase email', async () => {
  const ui = await screen({ seismikMail: true });
  await ui.click('email-register');
  ui.fill();
  await ui.submit();
  assert.deepEqual(ui.mail, [['verify-request', { id_token: 'opaque-id-token' }]]);
  assert.equal(ui.calls.some(([name]) => name === 'verify-email'), false);

  const recovery = await screen({ seismikMail: true });
  await recovery.click('email-recover');
  recovery.fill();
  await recovery.submit();
  assert.deepEqual(recovery.mail, [['reset-request', { email: 'test@example.invalid' }]]);
  assert.equal(recovery.calls.some(([name]) => name === 'recovery'), false);
});

test('when Seismik mail is unavailable the Firebase email is used as a fallback', async () => {
  const ui = await screen();
  await ui.click('email-register');
  ui.fill();
  await ui.submit();
  assert.equal(ui.mail.length, 1);
  assert.equal(ui.calls.some(([name]) => name === 'verify-email'), true);

  const recovery = await screen();
  await recovery.click('email-recover');
  recovery.fill();
  await recovery.submit();
  assert.equal(recovery.calls.some(([name]) => name === 'recovery'), true);
});

test('coming from My account the link is implicit and the page says which account will be linked', async () => {
  const ui = await screen({ search: '?link=1' });
  assert.equal(ui.node('link-account').checked, true);
  assert.equal(ui.node('link-label').hidden, true, 'la casilla confusa no se muestra');
  assert.equal(ui.node('link-help').hidden, true);
  assert.match(ui.node('link-context').textContent, /Se vinculará a la cuenta de Ana \(ana@example.test\)/);
  assert.equal(ui.node('email-title').textContent, 'Vincular un correo a tu cuenta');
  assert.equal(ui.node('email-submit').textContent, 'Vincular este correo');

  const plain = await screen();
  assert.equal(plain.node('link-account').checked, false);
  assert.equal(plain.node('email-title').textContent, 'Iniciar sesión con correo');
});

test('linking without a session or with an old one offers to sign in again and continue, before asking for anything', async () => {
  const none = await screen({ search: '?link=1', center: null });
  assert.match(none.node('email-message').textContent, /No encontramos tu sesión/);
  assert.equal(none.node('link-next').hidden, false);
  assert.equal(none.node('link-next').href, '/v1/oauth/account/login?next=link-email');

  const old = await screen({ search: '?link=1', center: {
    name: 'Ana', email: 'ana@example.test', current_method: 'google', recent_login: false,
    methods: [{ id: 'email', linked: false, primary: false }],
  } });
  assert.match(old.node('email-message').textContent, /más de 10 minutos/);
  assert.equal(old.node('link-next').href, '/v1/oauth/account/login?next=link-email');
});

test('an account that already has an email is told so and sent back, instead of asking for Google', async () => {
  const ui = await screen({ search: '?link=1', center: {
    name: 'Ana', email: 'ana@example.test', current_method: 'email', recent_login: true,
    methods: [{ id: 'email', linked: true, primary: false }],
  } });
  assert.match(ui.node('email-message').textContent, /ya tiene un correo vinculado/);
  assert.doesNotMatch(ui.node('email-message').textContent, /Google/);
  assert.equal(ui.node('link-next').href, '/account/');
  assert.equal(ui.node('email-form').hidden, true);
});

test('structured link errors show their message and the next step', async () => {
  const ui = await screen({ search: '?link=1', exchangeError: { code: 'link_conflict', message: 'Ese correo ya tiene su propia cuenta de Seismik con datos. No fusionamos cuentas.' } });
  ui.fill();
  await ui.submit();
  assert.match(ui.node('email-message').textContent, /No fusionamos cuentas/);
  assert.equal(ui.node('link-next').href, '/account/');

  const reauth = await screen({ search: '?link=1', exchangeError: { code: 'link_reauth', message: 'Por seguridad, vuelve a iniciar sesión.' } });
  reauth.fill();
  await reauth.submit();
  assert.equal(reauth.node('link-next').href, '/v1/oauth/account/login?next=link-email');

  const plain = await screen({ exchangeError: 'Algo salió mal en el servidor' });
  plain.fill();
  await plain.submit();
  assert.match(plain.node('email-message').textContent, /Algo salió mal/);
  assert.equal(plain.node('link-next').hidden, true);
});

test('after signing in from My account the page follows the account destinations and nothing else', async () => {
  const ok = await screen({ redirect: 'https://auth.seismik.org/account/' });
  ok.fill();
  await ok.submit();
  assert.deepEqual(ok.calls.filter(([name]) => name === 'redirect'), [['redirect', 'https://auth.seismik.org/account/']]);

  const erase = await screen({ redirect: 'https://seismik.org/delete-account/#confirmar' });
  erase.fill();
  await erase.submit();
  assert.equal(erase.calls.some(([name]) => name === 'redirect'), true);

  const evil = await screen({ redirect: 'https://evil.example/account/' });
  evil.fill();
  await evil.submit();
  assert.equal(evil.calls.some(([name]) => name === 'redirect'), false);
  assert.match(evil.node('email-message').textContent, /Destino de acceso no permitido/);
});
