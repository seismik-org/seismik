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
let busy = false;
const actionSettings = { url: "https://auth.seismik.org/id", handleCodeInApp: false };
function message(text, error = false) {
  $("email-message").textContent = text;
  $("email-message").hidden = false;
  $("email-message").dataset.error = String(error);
}
async function run(action) {
  if (busy) return;
  busy = true;
  $("email-form").setAttribute("aria-busy", "true");
  document.querySelectorAll("#email-form button").forEach((b) => { b.disabled = true; });
  message("Procesando…");
  try { await action(); }
  catch (error) {
    const code = error?.code;
    message(code === "auth/too-many-requests" ? "Demasiados intentos. Espera unos minutos."
      : code === "auth/network-request-failed" ? "No se pudo conectar. Comprueba tu conexión."
      : code === "auth/weak-password" || code === "auth/password-does-not-meet-requirements" ? "Usa al menos 12 caracteres y cumple los requisitos de contraseña."
      : error?.safeMessage || "No se pudo completar el acceso. Revisa los datos o recupera tu contraseña.", true);
  } finally {
    $("password").value = "";
    busy = false;
    $("email-form").setAttribute("aria-busy", "false");
    document.querySelectorAll("#email-form button").forEach((b) => { b.disabled = false; });
  }
}
async function finish() {
  await reload(auth.currentUser);
  if (!auth.currentUser.emailVerified) {
    $("email-verify").hidden = false;
    $("email-check").hidden = false;
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
  $("email-form").addEventListener("submit", (event) => {
    event.preventDefault();
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
      await signInWithEmailAndPassword(auth, $("email").value.trim(), $("password").value);
      await finish();
    });
  });
  $("email-register").addEventListener("click", () => run(async () => {
    if (!$("email-form").reportValidity()) return;
    if ($("password").value.length < 12) throw { code: "auth/weak-password" };
    try {
      const { user } = await createUserWithEmailAndPassword(auth, $("email").value.trim(), $("password").value);
      await sendEmailVerification(user, actionSettings);
    } catch (error) {
      if (error.code !== "auth/email-already-in-use") throw error;
    }
    $("email-verify").hidden = false;
    $("email-check").hidden = false;
    message("Si el registro puede completarse, recibirás un enlace de verificación. Si ya tienes acceso, entra o recupera tu contraseña.");
  }));
  $("email-recover").addEventListener("click", () => run(async () => {
    if (!$("email").reportValidity()) return;
    try { await sendPasswordResetEmail(auth, $("email").value.trim(), actionSettings); }
    catch (error) { if (error.code !== "auth/user-not-found") throw error; }
    message("Si el correo tiene acceso, recibirás instrucciones de Seismik para recuperar la contraseña.");
  }));
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
      message("Cambio de correo confirmado. Ya puedes iniciar sesión en Seismik.");
    } else if (params.get("mode") === "resetPassword") {
      await verifyPasswordResetCode(auth, code);
      resetting = true;
      $("email").required = false;
      $("email").hidden = true;
      document.querySelector('label[for="email"]').hidden = true;
      $("password").autocomplete = "new-password";
      $("link-label").hidden = true;
      document.querySelector(".email-actions").hidden = true;
      $("email-submit").textContent = "Guardar nueva contraseña";
      message("Escribe tu nueva contraseña (al menos 12 caracteres).");
    } else throw { safeMessage: "Este enlace no es válido. Solicita uno nuevo." };
    // Do not retain email action codes in browser history or outgoing links.
    history.replaceState(null, "", location.pathname);
  });
}
initialize().catch(() => message("El acceso con correo no está disponible temporalmente.", true));
