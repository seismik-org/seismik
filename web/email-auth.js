// Passwords go directly to Firebase; Seismik only receives a verified ID token.
import { initializeApp } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-app.js";
import { getAuth, inMemoryPersistence, setPersistence, signInWithEmailAndPassword,
  createUserWithEmailAndPassword, sendEmailVerification, sendPasswordResetEmail,
  signOut, reload, applyActionCode, verifyPasswordResetCode, confirmPasswordReset,
} from "https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const flowId = params.get("flow_id");
let auth;
let resetting = false;
let mode = "login";
let busy = false;
const actionSettings = { url: "https://auth.seismik.org/id", handleCodeInApp: false };
// Los correos de verificación y recuperación salen de Seismik (diseño propio y enlace directo a esta página).
// Si ese envío no está disponible, se usa el correo de Firebase: nadie se queda sin poder entrar.
async function viaSeismik(path, payload) {
  try {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    return response.ok;
  } catch (_) {
    return false;
  }
}
async function sendVerification(user) {
  if (await viaSeismik("/v1/oauth/email/verify-request", { id_token: await user.getIdToken() })) return;
  await sendEmailVerification(user, actionSettings);
}
async function sendRecovery(email) {
  if (await viaSeismik("/v1/oauth/email/reset-request", { email })) return;
  try { await sendPasswordResetEmail(auth, email, actionSettings); }
  catch (error) { if (error.code !== "auth/user-not-found") throw error; }
}
const LINK_RETRY = ["link_no_session", "link_reauth"];
const LINK_BACK = ["link_same", "link_has_email", "link_taken", "link_conflict"];
// Debajo del mensaje: el paso siguiente, para que nadie se quede en un callejón.
function nextStep(code) {
  const link = $("link-next");
  if (!link) return;
  if (LINK_RETRY.includes(code)) {
    link.href = "/v1/oauth/account/login?next=link-email";
    link.textContent = "Volver a iniciar sesión y continuar la vinculación";
    link.hidden = false;
  } else if (LINK_BACK.includes(code)) {
    link.href = "/account/";
    link.textContent = "Volver a Mi cuenta";
    link.hidden = false;
  } else {
    link.hidden = true;
  }
}
function message(text, error = false) {
  $("email-message").textContent = text;
  $("email-message").hidden = false;
  $("email-message").dataset.error = String(error);
}
function showMode(next) {
  mode = next;
  const register = mode === "register";
  const recover = mode === "recover";
  const linking = params.get("link") === "1";
  $("email-title").textContent = register ? "Crear cuenta con correo" : recover ? "Recuperar contraseña"
    : linking ? "Vincular un correo a tu cuenta" : "Iniciar sesión con correo";
  $("email-description").textContent = register
    ? (linking ? "Crea la cuenta de correo que quieres vincular. Te enviaremos un correo para confirmarla; cuando lo hagas, vuelve a «Mi cuenta» y pulsa «Vincular»."
      : "Elige una contraseña y confirma tu correo antes de acceder a Seismik.")
    : recover ? "Te enviaremos un enlace para elegir una nueva contraseña."
    : linking ? "Entra con el correo y la contraseña que quieres añadir. Se vinculará a la cuenta con la que ya iniciaste sesión."
    : "Introduce el correo y la contraseña de tu cuenta.";
  $("email-login").setAttribute("aria-pressed", String(mode === "login"));
  $("email-register").setAttribute("aria-pressed", String(register));
  $("password-fields").hidden = recover;
  $("password").required = !recover;
  $("password").disabled = recover;
  $("password").minLength = register ? 12 : 0;
  $("password").autocomplete = register ? "new-password" : "current-password";
  $("password").value = "";
  $("password-hint").hidden = !register;
  $("confirmation-fields").hidden = !register;
  $("password-confirm").required = register;
  $("password-confirm").disabled = !register;
  $("password-confirm").value = "";
  // Desde «Mi cuenta» el enlace es implícito: no se muestra la casilla ni su texto, que confundían.
  $("link-label").hidden = mode !== "login" || linking;
  $("link-help").hidden = recover || linking;
  $("email-recover").hidden = mode !== "login";
  $("email-back").hidden = !recover;
  $("email-submit").textContent = register ? "Crear cuenta y enviar verificación" : recover ? "Enviar enlace de recuperación" : linking ? "Vincular este correo" : "Iniciar sesión";
  $("email-message").hidden = true;
  $("verification-actions").hidden = true;
  nextStep();
}
async function run(action, pending = "Procesando…") {
  if (busy) return;
  busy = true;
  $("email-form").setAttribute("aria-busy", "true");
  document.querySelectorAll("#email-access button").forEach((b) => { b.disabled = true; });
  const label = $("email-submit").textContent;
  $("email-submit").textContent = pending;
  message(pending);
  try { await action(); }
  catch (error) {
    const code = error?.code;
    message(code === "auth/too-many-requests" ? "Demasiados intentos. Espera unos minutos."
      : code === "auth/network-request-failed" ? "No se pudo conectar. Comprueba tu conexión."
      : code === "auth/weak-password" || code === "auth/password-does-not-meet-requirements" ? "Usa al menos 12 caracteres y cumple los requisitos de contraseña."
      : code === "auth/operation-not-allowed" ? "El acceso con correo no está disponible temporalmente. Inténtalo más tarde."
      : code === "auth/expired-action-code" || code === "auth/invalid-action-code" ? "Este enlace expiró o no es válido. Solicita uno nuevo."
      : error?.safeMessage || "No se pudo completar el acceso. Revisa los datos o recupera tu contraseña.", true);
    nextStep(error?.linkCode);
  } finally {
    if ($("email-message").textContent === pending) message("Revisa los campos para continuar.", true);
    $("password").value = "";
    $("password-confirm").value = "";
    $("email-submit").textContent = label;
    busy = false;
    $("email-form").setAttribute("aria-busy", "false");
    document.querySelectorAll("#email-access button").forEach((b) => { b.disabled = false; });
  }
}
async function finish() {
  if (!auth.currentUser) throw { safeMessage: "Primero inicia sesión con tu correo y contraseña para comprobar la verificación." };
  await reload(auth.currentUser);
  if (!auth.currentUser.emailVerified) {
    $("verification-actions").hidden = false;
    message("Verifica tu correo con el enlace recibido. Después pulsa «Ya verifiqué mi correo».");
    return;
  }
  const token = await auth.currentUser.getIdToken(true);
  const response = await fetch("/v1/oauth/email/exchange", {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_token: token, flow_id: flowId, link: $("link-account").checked }),
  });
  const result = await response.json();
  if (!response.ok) {
    const detail = result.detail;
    throw { safeMessage: (typeof detail === "string" ? detail : detail?.message) || "No se pudo completar el acceso.", linkCode: detail?.code };
  }
  await signOut(auth);
  const target = new URL(result.redirect);
  if (!["https://devs.seismik.org", "https://admin.seismik.org", "https://waves.seismik.org", "https://auth.seismik.org", "https://seismik.org"].includes(target.origin) && !(flowId && target.protocol === "seismik:" && target.host === "auth" && target.pathname === "/callback")) {
    throw { safeMessage: "Destino de acceso no permitido." };
  }
  location.assign(target.href);
}

// Viene de «Mi cuenta»: se comprueba antes de pedir nada para no hacer perder tiempo a nadie.
async function prepareLinking() {
  $("link-account").checked = true;
  // Esta página, desde «Mi cuenta», sólo sirve para vincular el correo: los botones de otros accesos
  // iniciarían una sesión distinta y harían perder el hilo.
  $("providers").hidden = true;
  $("auth-title").textContent = "Mi cuenta";
  document.querySelector(".auth-copy").hidden = true;
  showMode("login");
  let info = null;
  try {
    const response = await fetch("/v1/oauth/account/center", { credentials: "include", headers: { Accept: "application/json" } });
    if (response.ok) info = await response.json();
  } catch (_) { /* sin red: el servidor responderá con el motivo al intentarlo */ }
  const context = $("link-context");
  if (!info) {
    message("No encontramos tu sesión de Seismik. Inicia sesión y se continuará con la vinculación.", true);
    nextStep("link_no_session");
    return;
  }
  const email = info.methods.find((method) => method.id === "email");
  context.textContent = `Se vinculará a la cuenta de ${info.name || info.email}${info.email ? ` (${info.email})` : ""}.`;
  context.hidden = false;
  if (email?.linked) {
    message(email.primary ? "Tu cuenta ya se creó con un correo y contraseña: no hay nada que vincular." : "Tu cuenta ya tiene un correo vinculado. Solo se puede vincular uno.", true);
    nextStep("link_same");
    $("email-form").hidden = true;
    $("email-navigation").hidden = true;
  } else if (!info.recent_login) {
    message("Han pasado más de 10 minutos desde que iniciaste sesión. Por seguridad, vuelve a iniciarla y la vinculación continuará sola.", true);
    nextStep("link_reauth");
  }
}
async function initialize() {
  const response = await fetch("/v1/oauth/email/config", { credentials: "include" });
  if (!response.ok) throw new Error("config");
  const config = await response.json();
  if (!config.enabled) return;
  auth = getAuth(initializeApp(config.firebase));
  auth.languageCode = "es";
  await setPersistence(auth, inMemoryPersistence);
  $("email-access").hidden = false;
  showMode("login");
  if (params.get("link") === "1") await prepareLinking();
  $("email-login").addEventListener("click", () => showMode("login"));
  $("email-register").addEventListener("click", () => showMode("register"));
  $("email-recover").addEventListener("click", () => showMode("recover"));
  $("email-back").addEventListener("click", () => showMode("login"));
  $("email-form").addEventListener("invalid", () => {
    message(mode === "register" ? "Completa el correo, una contraseña de al menos 12 caracteres y su confirmación." : "Revisa los campos indicados para continuar.", true);
  }, true);
  $("email-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!$("email-form").reportValidity()) {
      message("Revisa los campos indicados para continuar.", true);
      return;
    }
    if (mode === "register" && $("password").value !== $("password-confirm").value) {
      message("Las contraseñas no coinciden. Revisa la confirmación.", true);
      return;
    }
    run(async () => {
      if (resetting) {
        if ($("password").value.length < 12) throw { code: "auth/weak-password" };
        await confirmPasswordReset(auth, params.get("oobCode"), $("password").value);
        await signOut(auth);
        message("Contraseña actualizada. Ya puedes entrar con tu nueva contraseña.");
        $("email-submit").disabled = true;
        location.replace("/id");
        return;
      }
      if (mode === "register") {
        if ($("password").value.length < 12) throw { code: "auth/weak-password" };
        let user;
        try {
          ({ user } = await createUserWithEmailAndPassword(auth, $("email").value.trim(), $("password").value));
        } catch (error) {
          if (error.code !== "auth/email-already-in-use") throw error;
        }
        if (user) {
          try { await sendVerification(user); }
          catch (_) {
            $("verification-actions").hidden = false;
            throw { safeMessage: "No se pudo enviar el correo de verificación. Puedes reenviarlo aquí o iniciar sesión más tarde para hacerlo." };
          }
        }
        $("verification-actions").hidden = false;
        message("Solicitud de registro completada. Revisa tu correo y la carpeta de spam. Si no recibes un enlace, inicia sesión o recupera tu contraseña.");
        return;
      }
      if (mode === "recover") {
        await sendRecovery($("email").value.trim());
        message("Si el correo tiene acceso, recibirás instrucciones de Seismik para recuperar la contraseña.");
        return;
      }
      await signInWithEmailAndPassword(auth, $("email").value.trim(), $("password").value);
      await finish();
    }, resetting ? "Guardando contraseña…" : mode === "register" ? "Creando cuenta…" : mode === "recover" ? "Enviando enlace…" : "Iniciando sesión…");
  });
  $("email-verify").addEventListener("click", () => run(async () => {
    if (!auth.currentUser) throw { safeMessage: "Entra con tu correo para reenviar la verificación." };
    await sendVerification(auth.currentUser);
    message("Enlace enviado. Revisa tu correo y la carpeta de spam.");
  }));
  $("email-check").addEventListener("click", () => run(finish));
  if (params.has("mode")) await run(async () => {
    const code = params.get("oobCode");
    if (["verifyEmail", "recoverEmail", "verifyAndChangeEmail"].includes(params.get("mode"))) {
      await applyActionCode(auth, code);
      message(params.get("mode") === "verifyEmail"
        ? "Correo verificado. Ya puedes iniciar sesión en Seismik."
        : "Cambio de correo confirmado. Ya puedes iniciar sesión en Seismik.");
    } else if (params.get("mode") === "resetPassword") {
      await verifyPasswordResetCode(auth, code);
      resetting = true;
      $("email-navigation").hidden = true;
      $("email-title").textContent = "Elegir nueva contraseña";
      $("email-description").textContent = "Usa al menos 12 caracteres para proteger tu cuenta.";
      $("email").required = false;
      $("email").hidden = true;
      document.querySelector('label[for="email"]').hidden = true;
      $("password").autocomplete = "new-password";
      $("link-label").hidden = true;
      $("link-help").hidden = true;
      document.querySelector(".email-actions").hidden = true;
      $("email-submit").textContent = "Guardar nueva contraseña";
      message("Escribe tu nueva contraseña (al menos 12 caracteres).");
    } else throw { safeMessage: "Este enlace no es válido. Solicita uno nuevo." };
    // Do not retain email action codes in browser history or outgoing links.
    history.replaceState(null, "", location.pathname);
  });
}
initialize().catch(() => message("El acceso con correo no está disponible temporalmente.", true));
