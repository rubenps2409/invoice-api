import { h, clear } from "./dom.js";
import { request, explain } from "./api.js";
import { text } from "./strings.js";
import { money, isoDate, isZero, negate } from "./format.js";
import { store } from "./store.js";
import { statusBadge } from "./extract.js";

const PAGE_SIZE = 25;

export function invoicesView(ctx) {
  const filters = { status: "", from: "", to: "" };
  let items = [];
  let hasMore = false;
  let loaded = false;

  const status = h(
    "select",
    { id: "f-status", onchange: () => reload() },
    h("option", { value: "" }, text.invoices.allStatuses),
    Object.entries(text.statuses).map(([value, label]) => h("option", { value }, label)),
  );
  const from = h("input", { id: "f-from", type: "date", onchange: () => reload() });
  const to = h("input", { id: "f-to", type: "date", onchange: () => reload() });
  const reset = h(
    "button",
    {
      class: "btn ghost",
      type: "button",
      onclick: () => {
        status.value = "";
        from.value = "";
        to.value = "";
        reload();
      },
    },
    text.invoices.reset,
  );
  const body = h("div", { class: "list-body", "aria-live": "polite" });

  function readFilters() {
    filters.status = status.value;
    filters.from = from.value;
    filters.to = to.value;
  }

  const anyFilter = () => Boolean(filters.status || filters.from || filters.to);

  function row(invoice) {
    const cur = invoice.currency;
    return h(
      "tr",
      null,
      h("td", { class: "nowrap" }, isoDate(invoice.issue_date)),
      h("td", { class: "mono" }, invoice.number),
      h("td", null, store.supplierName(invoice.supplier_id)),
      h("td", null, store.categoryName(invoice.category_id) ?? h("span", { class: "muted" }, "—")),
      h("td", { class: "num" }, money(invoice.base_amount, cur)),
      h("td", { class: "num" }, money(invoice.tax_amount, cur)),
      h(
        "td",
        { class: "num" },
        isZero(invoice.withholding_amount)
          ? h("span", { class: "muted" }, "—")
          : money(negate(invoice.withholding_amount), cur),
      ),
      h("td", { class: "num strong" }, money(invoice.total_amount, cur)),
      h("td", null, statusBadge(invoice.status)),
    );
  }

  function draw({ error, busy } = {}) {
    clear(body);
    if (error) {
      body.append(h("p", { class: "alert", role: "alert" }, error));
      return;
    }
    if (loaded && items.length === 0) {
      body.append(
        h(
          "div",
          { class: "empty" },
          h("p", null, anyFilter() ? text.invoices.empty : text.invoices.emptyFirst),
          anyFilter()
            ? null
            : h("button", { class: "btn primary", type: "button", onclick: () => ctx.go("extract") }, text.invoices.goExtract),
        ),
      );
      return;
    }
    if (!loaded) {
      body.append(h("p", { class: "muted" }, text.invoices.loading));
      return;
    }
    const c = text.invoices.columns;
    body.append(
      h(
        "div",
        { class: "table-wrap" },
        h(
          "table",
          { class: "grid" },
          h("caption", { class: "sr-only" }, text.invoices.title),
          h(
            "thead",
            null,
            h(
              "tr",
              null,
              h("th", { scope: "col" }, c.date),
              h("th", { scope: "col" }, c.number),
              h("th", { scope: "col" }, c.supplier),
              h("th", { scope: "col" }, c.category),
              h("th", { scope: "col", class: "num" }, c.base),
              h("th", { scope: "col", class: "num" }, c.tax),
              h("th", { scope: "col", class: "num" }, c.withholding),
              h("th", { scope: "col", class: "num" }, c.total),
              h("th", { scope: "col" }, c.status),
            ),
          ),
          h("tbody", null, items.map(row)),
        ),
      ),
    );
    if (hasMore) {
      body.append(
        h(
          "div",
          { class: "more" },
          h(
            "button",
            { class: "btn ghost", type: "button", disabled: Boolean(busy), onclick: () => fetchPage() },
            busy ? text.invoices.loading : text.invoices.loadMore,
          ),
        ),
      );
    }
  }

  async function fetchPage() {
    draw({ busy: true });
    try {
      const page = await request("GET", "/invoices", {
        query: {
          status: filters.status,
          date_from: filters.from,
          date_to: filters.to,
          skip: items.length,
          limit: PAGE_SIZE,
        },
      });
      items = items.concat(page);
      hasMore = page.length === PAGE_SIZE;
      loaded = true;
      draw();
    } catch (error) {
      draw({ error: explain(error) });
    }
  }

  function reload() {
    readFilters();
    items = [];
    hasMore = false;
    loaded = false;
    fetchPage();
  }

  // Names first (the API returns ids), then the first page.
  store
    .load()
    .catch(() => {})
    .then(reload);

  return h(
    "section",
    { class: "panel wide", "aria-labelledby": "invoices-title" },
    h("h1", { id: "invoices-title" }, text.invoices.title),
    h(
      "div",
      { class: "filters" },
      h("div", null, h("label", { for: "f-status" }, text.invoices.status), status),
      h("div", null, h("label", { for: "f-from" }, text.invoices.from), from),
      h("div", null, h("label", { for: "f-to" }, text.invoices.to), to),
      reset,
    ),
    body,
  );
}
