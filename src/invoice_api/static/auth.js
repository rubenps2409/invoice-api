import { h } from "./dom.js";
import { request, explain, session } from "./api.js";
import { text } from "./strings.js";

// The sign-in / create-account screen. `onSignedIn` runs once a token is stored.
export function authView({ message, onSignedIn }) {
  let mode = "signin";

  const error = h("p", { class: "alert", role: "alert", hidden: true });
  const info = h("p", { class: "info", role: "status", hidden: !message }, message ?? "");
  const email = h("input", {
    id: "email",
    type: "email",
    name: "email",
    required: true,
    autocomplete: "email",
    maxLength: 255,
    spellcheck: false,
  });
  const password = h("input", {
    id: "password",
    type: "password",
    name: "password",
    required: true,
    minLength: 8,
    maxLength: 128,
    autocomplete: "current-password",
  });
  const hint = h("p", { class: "hint", id: "password-hint", hidden: true }, text.auth.passwordHint);
  const submit = h("button", { class: "btn primary block", type: "submit" }, text.auth.signIn);

  const tabs = {
    signin: h(
      "button",
      { type: "button", class: "seg", "aria-pressed": "true", onclick: () => setMode("signin") },
      text.auth.signInTab,
    ),
    register: h(
      "button",
      { type: "button", class: "seg", "aria-pressed": "false", onclick: () => setMode("register") },
      text.auth.registerTab,
    ),
  };

  function setMode(next) {
    mode = next;
    tabs.signin.setAttribute("aria-pressed", String(mode === "signin"));
    tabs.register.setAttribute("aria-pressed", String(mode === "register"));
    submit.textContent = mode === "signin" ? text.auth.signIn : text.auth.register;
    password.autocomplete = mode === "signin" ? "current-password" : "new-password";
    hint.hidden = mode === "signin";
    error.hidden = true;
    info.hidden = true;
  }

  function setBusy(busy) {
    submit.disabled = busy;
    email.disabled = busy;
    password.disabled = busy;
    if (busy) submit.textContent = text.auth.working;
    else submit.textContent = mode === "signin" ? text.auth.signIn : text.auth.register;
  }

  async function onSubmit(event) {
    event.preventDefault();
    error.hidden = true;
    info.hidden = true;
    const credentials = { email: email.value.trim(), password: password.value };
    setBusy(true);
    try {
      if (mode === "register") {
        await request("POST", "/auth/register", { json: credentials, auth: false });
      }
      const token = await request("POST", "/auth/login", {
        form: { username: credentials.email, password: credentials.password },
        auth: false,
      });
      session.save(token.access_token);
      onSignedIn();
    } catch (failure) {
      error.textContent = explain(failure, { action: mode === "signin" ? "login" : "register" });
      error.hidden = false;
      setBusy(false);
      password.focus();
    }
  }

  return h(
    "main",
    { class: "auth", id: "main" },
    h(
      "section",
      { class: "card auth-card", "aria-labelledby": "auth-title" },
      h(
        "p",
        { class: "wordmark" },
        text.brand,
        h("span", null, text.brandSuffix),
      ),
      h("h1", { id: "auth-title" }, text.auth.intro),
      h("div", { class: "segmented", role: "group", "aria-label": "Account" }, tabs.signin, tabs.register),
      info,
      h(
        "form",
        { onsubmit: onSubmit, novalidate: false },
        h("label", { for: "email" }, text.auth.email),
        email,
        h("label", { for: "password" }, text.auth.password),
        password,
        hint,
        error,
        submit,
      ),
      h("p", { class: "fine" }, text.auth.demoNote),
    ),
  );
}
