// A tiny element builder. It never parses HTML: strings become text nodes, so whatever
// the API returns (supplier names, invoice text) cannot turn into markup.

const FORBIDDEN = new Set(["innerHTML", "outerHTML"]);

export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(props ?? {})) {
    if (value === undefined || value === null || value === false) continue;
    if (FORBIDDEN.has(name)) throw new Error(`h(): ${name} is not allowed`);
    if (name === "class") {
      el.className = value;
    } else if (name.startsWith("on") && typeof value === "function") {
      el.addEventListener(name.slice(2).toLowerCase(), value);
    } else if (name in el && !name.includes("-")) {
      el[name] = value;
    } else {
      el.setAttribute(name, value === true ? "" : String(value));
    }
  }
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    el.append(child);
  }
  return el;
}

export function clear(el) {
  el.replaceChildren();
  return el;
}

// Moves the keyboard and screen-reader focus to an element that is not focusable by default.
export function focusHeading(el) {
  if (!el) return;
  el.setAttribute("tabindex", "-1");
  el.focus({ preventScroll: false });
}
