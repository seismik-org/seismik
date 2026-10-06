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
function message(text, error = false) {
  $("email-message").textContent = text;
  $("email-message").hidden = false;
  $("email-message").dataset.error = String(error);
}
function showMode(next) {
  mode = next;
  const register = mode === "register";
  const recover = mode === "recover";
  $("email-title").textContent = register ? "Crear cuenta con correo" : recover ? "Recuperar contraseña" : "Iniciar sesión con correo";
  $("email-description").textContent = register
    ? "Elige una contraseña y confirma tu correo antes de acceder a Seismik."
    : recover ? "Te enviaremos un enlace para elegir una nueva contraseña."
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
  $("link-label").hidden = mode !== "login";
  $("link-help").hidden = recover;
  $("email-recover").hidden = mode !== "login";
  $("email-back").hidden = !recover;
  $("email-submit").textContent = register ? "Crear cuenta y enviar verificación" : recover ? "Enviar enlace de recuperación" : "Iniciar sesión";
  $("email-message").hidden = true;
  $("verification-actions").hidden = true;
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
  if (!response.ok) throw { safeMessage: result.detail || "No se pudo completar el acceso." };
  await signOut(auth);
  const target = new URL(result.redirect);
  if (target.origin !== "https://devs.seismik.org" && !(flowId && target.protocol === "seismik:" && target.host === "auth" && target.pathname === "/callback")) {
    throw { safeMessage: "Destino de acceso no permitido." };
  }
  location.assign(target.href);
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
          try { await sendEmailVerification(user, actionSettings); }
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
        try { await sendPasswordResetEmail(auth, $("email").value.trim(), actionSettings); }
        catch (error) { if (error.code !== "auth/user-not-found") throw error; }
        message("Si el correo tiene acceso, recibirás instrucciones de Seismik para recuperar la contraseña.");
        return;
      }
      await signInWithEmailAndPassword(auth, $("email").value.trim(), $("password").value);
      await finish();
    }, resetting ? "Guardando contraseña…" : mode === "register" ? "Creando cuenta…" : mode === "recover" ? "Enviando enlace…" : "Iniciando sesión…");
  });
  $("email-verify").addEventListener("click", () => run(async () => {
    if (!auth.currentUser) throw { safeMessage: "Entra con tu correo para reenviar la verificación." };
    await sendEmailVerification(auth.currentUser, actionSettings);
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
