import { h, clear, focusHeading } from "./dom.js";
import { request, session, setSlowHandler, setUnauthorizedHandler } from "./api.js";
import { text } from "./strings.js";
import { usd } from "./format.js";
import { store } from "./store.js";
import { authView } from "./auth.js";
import { extractView } from "./extract.js";
import { invoicesView } from "./invoices.js";
import { categoriesView } from "./categories.js";

const root = document.getElementById("app");
const notice = document.getElementById("notice");

const views = {
  extract: extractView,
  invoices: invoicesView,
  categories: categoriesView,
};
const DEFAULT_TAB = "extract";

let user = null;
let usageEls = null;

// The server sleeps on a free plan: tell the person why the page is waiting.
setSlowHandler((slow) => {
  notice.textContent = slow ? text.notice.waking : "";
  notice.hidden = !slow;
});

setUnauthorizedHandler(() => showAuth(text.auth.expired));

function currentTab() {
  const tab = window.location.hash.slice(1);
  // hasOwn, not `in`: #constructor or #__proto__ must not pick something from Object.prototype.
  return Object.hasOwn(views, tab) ? tab : DEFAULT_TAB;
}

function go(tab) {
  if (window.location.hash.slice(1) === tab) renderPanel();
  else window.location.hash = tab;
}

async function refreshUsage() {
  if (!usageEls) return;
  try {
    const usage = await request("GET", "/usage");
    const spent = Number(usage.estimated_spent_usd);
    const budget = Number(usage.budget_usd);
    const share = budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;
    usageEls.value.textContent = `${usd(usage.estimated_spent_usd)} ${text.shell.usageOf} ${usd(usage.budget_usd)}`;
    usageEls.fill.style.width = `${share}%`;
    usageEls.meter.setAttribute("aria-valuenow", String(Math.round(share)));
    usageEls.meter.classList.toggle("high", share >= 80);
    usageEls.box.title = text.shell.usageReset;
  } catch {
    /* the meter is a convenience: stay quiet if it cannot load */
  }
}

function renderPanel() {
  const tab = currentTab();
  const main = document.getElementById("main");
  if (!main) return;
  for (const link of document.querySelectorAll(".tabs a")) {
    if (link.dataset.tab === tab) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  clear(main).append(views[tab]({ go, refreshUsage }));
  focusHeading(main.querySelector("h1"));
}

function signOut(message) {
  session.clear();
  store.reset();
  showAuth(message);
}

function showAuth(message) {
  user = null;
  usageEls = null;
  clear(root).append(
    authView({
      message,
      onSignedIn: () => {
        start();
      },
    }),
  );
}

function shell() {
  const fill = h("span", { class: "meter-fill" });
  const meter = h(
    "div",
    { class: "meter", role: "meter", "aria-label": text.shell.usageLabel, "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": "0" },
    fill,
  );
  const value = h("span", { class: "usage-value" }, "—");
  const box = h("div", { class: "usage" }, h("span", { class: "usage-label" }, text.shell.usageLabel), value, meter);
  usageEls = { box, value, fill, meter };

  const links = Object.entries(text.shell.tabs).map(([tab, label]) =>
    h("a", { href: `#${tab}`, "data-tab": tab }, label),
  );

  return [
    h("a", { class: "skip", href: "#main" }, "Skip to content"),
    h(
      "header",
      { class: "bar" },
      h("p", { class: "wordmark" }, text.brand, h("span", null, text.brandSuffix)),
      box,
      h(
        "div",
        { class: "who" },
        h("span", { class: "who-email" }, user.email),
        h("button", { class: "btn ghost small", type: "button", onclick: () => signOut(text.auth.signedOut) }, text.shell.signOut),
      ),
    ),
    h("nav", { class: "tabs", "aria-label": "Sections" }, links),
    h("div", { id: "main", class: "main" }),
  ];
}

async function start() {
  if (!session.token) {
    showAuth();
    return;
  }
  try {
    user = await request("GET", "/users/me");
  } catch {
    // A 401 already sent the person to the sign-in screen; anything else is shown there too.
    if (!session.token) return;
    showAuth(text.errors.network);
    return;
  }
  clear(root).append(...shell());
  renderPanel();
  refreshUsage();
}

window.addEventListener("hashchange", () => {
  if (user) renderPanel();
});

start();
