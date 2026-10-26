import { h, clear, focusHeading } from "./dom.js";
import { request, explain } from "./api.js";
import { text } from "./strings.js";
import { money, isoDate, isZero, negate } from "./format.js";
import { store } from "./store.js";

// The server's default MAX_INVOICE_TEXT_CHARS. If it is configured differently the API
// answers 422 with its own message.
const MAX_CHARS = 20_000;

export function statusBadge(status) {
  return h("span", { class: `badge ${status}` }, text.statuses[status] ?? status);
}

function slip(invoice, { onAnother, onViewAll }) {
  const supplier = store.suppliers.get(invoice.supplier_id);
  const category = store.categoryName(invoice.category_id);
  const currency = invoice.currency;
  const title = h("h2", { id: "slip-title" }, `Invoice ${invoice.number}`);

  const fact = (label, value) => [h("dt", null, label), h("dd", null, value)];
  const amount = (label, value, extra = "") =>
    h("tr", { class: extra }, h("th", { scope: "row" }, label), h("td", null, value));

  const rows = [
    amount(text.fields.base, money(invoice.base_amount, currency)),
    amount(text.fields.tax, money(invoice.tax_amount, currency)),
  ];
  if (!isZero(invoice.withholding_amount)) {
    rows.push(amount(text.fields.withholding, money(negate(invoice.withholding_amount), currency)));
  }
  rows.push(amount(text.fields.total, money(invoice.total_amount, currency), "total"));

  return h(
    "article",
    { class: "slip", "aria-labelledby": "slip-title" },
    h(
      "header",
      { class: "slip-head" },
      h("div", null, h("p", { class: "eyebrow" }, text.extract.resultTitle), title),
      statusBadge(invoice.status),
    ),
    h(
      "dl",
      { class: "facts" },
      fact(text.fields.supplier, supplier?.name ?? store.supplierName(invoice.supplier_id)),
      supplier?.tax_id ? fact(text.fields.taxId, supplier.tax_id) : [],
      fact(text.fields.issued, isoDate(invoice.issue_date)),
      fact(text.fields.category, category ?? text.fields.none),
    ),
    h("table", { class: "amounts" }, h("tbody", null, rows)),
    h("p", { class: "checked" }, text.extract.checked),
    h(
      "div",
      { class: "actions" },
      h("button", { class: "btn primary", type: "button", onclick: onViewAll }, text.extract.viewAll),
      h("button", { class: "btn ghost", type: "button", onclick: onAnother }, text.extract.clear),
    ),
  );
}

export function extractView(ctx) {
  let sampleIndex = 0;

  const input = h("textarea", {
    id: "invoice-text",
    rows: 12,
    maxLength: MAX_CHARS,
    placeholder: text.extract.placeholder,
    spellcheck: false,
    "aria-describedby": "counter",
  });
  const counter = h("span", { id: "counter", class: "counter" }, text.extract.counter(0, MAX_CHARS));
  const result = h("div", { class: "result", "aria-live": "polite" });
  const submit = h("button", { class: "btn primary", type: "submit" }, text.extract.submit);
  const sample = h(
    "button",
    {
      class: "btn ghost",
      type: "button",
      onclick: () => {
        input.value = text.samples[sampleIndex % text.samples.length].body;
        sampleIndex += 1;
        updateCounter();
        input.focus();
      },
    },
    text.extract.sample,
  );

  function updateCounter() {
    counter.textContent = text.extract.counter(input.value.length, MAX_CHARS);
  }
  input.addEventListener("input", updateCounter);

  function setBusy(busy) {
    submit.disabled = busy;
    sample.disabled = busy;
    input.readOnly = busy;
  }

  function show(...nodes) {
    clear(result).append(...nodes);
  }

  function working() {
    show(
      h(
        "div",
        { class: "working", role: "status" },
        h("span", { class: "spinner", "aria-hidden": "true" }),
        h("div", null, h("strong", null, text.extract.working), h("p", { class: "hint" }, text.extract.workingHint)),
      ),
    );
  }

  function failure(message) {
    show(h("p", { class: "alert", role: "alert" }, message));
  }

  async function run(event) {
    event.preventDefault();
    const body = input.value.trim();
    if (!body) {
      failure(text.extract.empty);
      input.focus();
      return;
    }
    setBusy(true);
    working();
    try {
      const invoice = await request("POST", "/invoices/extract", { json: { text: body } });
      // The extraction may have created a supplier; the names come from the lists.
      try {
        await store.load();
      } catch {
        /* the slip falls back to ids */
      }
      ctx.refreshUsage();
      show(
        slip(invoice, {
          onAnother: () => {
            clear(result);
            input.value = "";
            updateCounter();
            input.focus();
          },
          onViewAll: () => ctx.go("invoices"),
        }),
      );
      focusHeading(result.querySelector("#slip-title"));
    } catch (error) {
      ctx.refreshUsage();
      failure(explain(error, { action: "extract" }));
    } finally {
      setBusy(false);
    }
  }

  return h(
    "section",
    { class: "panel", "aria-labelledby": "extract-title" },
    h("h1", { id: "extract-title" }, text.extract.title),
    h("p", { class: "lead" }, text.extract.lead),
    h(
      "form",
      { class: "extract-form", onsubmit: run },
      h("label", { for: "invoice-text" }, text.extract.label),
      input,
      h("div", { class: "form-foot" }, counter, h("div", { class: "actions" }, sample, submit)),
    ),
    result,
  );
}
