import { h, clear } from "./dom.js";
import { request, explain, listAll } from "./api.js";
import { text } from "./strings.js";
import { store } from "./store.js";

const CONFIRM_WINDOW_MS = 4000;

export function categoriesView() {
  let items = [];
  let armed = null; // id of the category whose delete button waits for a second click
  let armedTimer = null;

  const message = h("p", { class: "info", role: "status", hidden: true });
  const alert = h("p", { class: "alert", role: "alert", hidden: true });
  const list = h("ul", { class: "chips" });
  const input = h("input", {
    id: "category-name",
    type: "text",
    maxLength: 100,
    required: true,
    placeholder: text.categories.placeholder,
    autocomplete: "off",
  });

  function say(kind, content) {
    message.hidden = kind !== "info";
    alert.hidden = kind !== "alert";
    (kind === "info" ? message : alert).textContent = content ?? "";
  }

  function disarm() {
    armed = null;
    clearTimeout(armedTimer);
  }

  function draw() {
    clear(list);
    if (items.length === 0) {
      list.append(h("li", { class: "muted" }, text.categories.empty));
      return;
    }
    for (const category of items) {
      const isArmed = armed === category.id;
      list.append(
        h(
          "li",
          { class: "chip" },
          h("span", null, category.name),
          h(
            "button",
            {
              class: isArmed ? "chip-btn danger" : "chip-btn",
              type: "button",
              "aria-label": `${isArmed ? text.categories.confirm : text.categories.delete} ${category.name}`,
              onclick: () => (isArmed ? remove(category) : arm(category)),
            },
            isArmed ? text.categories.confirm : text.categories.delete,
          ),
        ),
      );
    }
  }

  function arm(category) {
    disarm();
    armed = category.id;
    armedTimer = setTimeout(() => {
      armed = null;
      draw();
    }, CONFIRM_WINDOW_MS);
    draw();
  }

  async function remove(category) {
    disarm();
    try {
      await request("DELETE", `/categories/${category.id}`);
      items = items.filter((c) => c.id !== category.id);
      store.categories.delete(category.id);
      say("info", text.categories.deleted(category.name));
    } catch (error) {
      say("alert", explain(error));
    }
    draw();
  }

  async function add(event) {
    event.preventDefault();
    const name = input.value.trim();
    if (!name) return;
    try {
      const created = await request("POST", "/categories", { json: { name } });
      items = [...items, created].sort((a, b) => a.name.localeCompare(b.name));
      store.categories.set(created.id, created);
      input.value = "";
      say("info", text.categories.added(created.name));
      draw();
    } catch (error) {
      say("alert", explain(error));
    }
    input.focus();
  }

  listAll("/categories")
    .then((all) => {
      items = all.sort((a, b) => a.name.localeCompare(b.name));
      draw();
    })
    .catch((error) => say("alert", explain(error)));

  return h(
    "section",
    { class: "panel", "aria-labelledby": "categories-title" },
    h("h1", { id: "categories-title" }, text.categories.title),
    h("p", { class: "lead" }, text.categories.lead),
    h(
      "form",
      { class: "inline-form", onsubmit: add },
      h("label", { for: "category-name" }, text.categories.label),
      h("div", { class: "inline-row" }, input, h("button", { class: "btn primary", type: "submit" }, text.categories.add)),
    ),
    message,
    alert,
    list,
  );
}
