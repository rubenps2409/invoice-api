// What the pages share: the user's suppliers and categories, so an invoice that only carries
// ids can be shown with names. The API has no endpoint for that join, and does not need one.

import { listAll } from "./api.js";

export const store = {
  suppliers: new Map(),
  categories: new Map(),

  async load() {
    const [suppliers, categories] = await Promise.all([
      listAll("/suppliers"),
      listAll("/categories"),
    ]);
    this.suppliers = new Map(suppliers.map((s) => [s.id, s]));
    this.categories = new Map(categories.map((c) => [c.id, c]));
  },

  supplierName(id) {
    return this.suppliers.get(id)?.name ?? `#${id}`;
  },

  categoryName(id) {
    if (id === null || id === undefined) return null;
    return this.categories.get(id)?.name ?? `#${id}`;
  },

  reset() {
    this.suppliers = new Map();
    this.categories = new Map();
  },
};
