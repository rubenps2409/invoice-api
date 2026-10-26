// Every piece of text the page shows, in one place so it can be translated.

export const text = {
  brand: "invoice",
  brandSuffix: "/api",

  auth: {
    signInTab: "Sign in",
    registerTab: "Create account",
    email: "Email",
    password: "Password",
    passwordHint: "At least 8 characters.",
    signIn: "Sign in",
    register: "Create account",
    working: "Please wait…",
    intro: "Paste the text of an invoice and get its data back, checked and stored.",
    demoNote:
      "This is a demo on a free plan. It sleeps when idle, so the first request can take up to a minute.",
    expired: "Your session expired. Please sign in again.",
    signedOut: "You have signed out.",
  },

  shell: {
    signOut: "Sign out",
    tabs: { extract: "Extract", invoices: "Invoices", categories: "Categories" },
    usageLabel: "Today's model spend",
    usageOf: "of",
    usageReset: "Resets at 00:00 UTC.",
  },

  notice: {
    waking: "The server was asleep and is waking up. This can take up to a minute…",
  },

  extract: {
    title: "Extract an invoice",
    lead: "Paste the invoice as plain text. The model reads it, the API checks that the amounts add up, and the invoice is stored as pending.",
    label: "Invoice text",
    placeholder: "Invoice no. 2026/17\nDate: 03/11/2026\n…",
    sample: "Use a sample",
    submit: "Extract invoice",
    working: "Reading the invoice…",
    workingHint: "A few seconds. The first request after a pause takes longer.",
    clear: "Extract another",
    viewAll: "View all invoices",
    counter: (n, max) => `${n.toLocaleString("en-US")} / ${max.toLocaleString("en-US")}`,
    empty: "Paste some text first.",
    resultTitle: "Stored as pending",
    checked:
      "Base + tax − withholding equals the total, and the total is printed in the text.",
  },

  invoices: {
    title: "Invoices",
    status: "Status",
    from: "From",
    to: "To",
    allStatuses: "All",
    reset: "Reset",
    loadMore: "Load more",
    loading: "Loading…",
    empty: "No invoices match.",
    emptyFirst: "No invoices yet. Extract your first one.",
    goExtract: "Extract an invoice",
    columns: {
      date: "Date",
      number: "Number",
      supplier: "Supplier",
      category: "Category",
      base: "Base",
      tax: "Tax",
      withholding: "Withholding",
      total: "Total",
      status: "Status",
    },
  },

  fields: {
    number: "Number",
    issued: "Issued",
    supplier: "Supplier",
    taxId: "Tax id",
    category: "Category",
    status: "Status",
    base: "Taxable base",
    tax: "Tax",
    withholding: "Withholding",
    total: "Total",
    none: "None",
  },

  statuses: {
    pending: "Pending",
    paid: "Paid",
    partially_paid: "Partially paid",
    cancelled: "Cancelled",
  },

  categories: {
    title: "Categories",
    lead: "The extractor only assigns a category from this list. An invoice whose category is not here is stored without one.",
    label: "New category",
    placeholder: "Software, Utilities, Travel…",
    add: "Add",
    empty: "No categories yet.",
    delete: "Delete",
    confirm: "Confirm",
    added: (name) => `Added “${name}”.`,
    deleted: (name) => `Deleted “${name}”.`,
  },

  errors: {
    network: "Could not reach the server. Check your connection and try again.",
    generic: "Something went wrong. Please try again.",
    credentials: "Incorrect email or password.",
    session: "Your session expired. Please sign in again.",
    tryAgainIn: (when) => `Try again in ${when}.`,
    tooMany: "Too many attempts.",
    extraction422: "No valid invoice could be extracted from this text.",
    extraction502: "The model service returned an error. Please try again later.",
    extraction503: "Extraction is temporarily unavailable.",
    extraction504: "The model took too long to answer. Please try again.",
  },

  samples: [
    {
      name: "Services with VAT",
      body: "FACTURA\nNº: F-2026-0042\nFecha: 15/10/2026\n\nEmisor: Estudio Lumbre Digital S.L.\nCIF: B12345678\nCalle Ejemplo 12, 28000 Madrid\n\nCliente: Taller Demo S.L.\nCIF: B87654321\n\nDescripción: Diseño y maquetación de sitio web\nBase imponible: 1.000,00 EUR\nIVA 21%: 210,00 EUR\nTOTAL: 1.210,00 EUR\n\nForma de pago: transferencia a 30 días.",
    },
    {
      name: "Freelancer with IRPF withholding",
      body: "FACTURA Nº 2026/17\nFecha de emisión: 03/11/2026\n\nProfesional: Marina Vela Ejemplo\nNIF: 12345678Z\n\nCliente: Agencia Demo S.L.\n\nHonorarios por traducción técnica ........ 800,00 EUR\nIVA (21%) ................................ 168,00 EUR\nRetención IRPF (15%) ..................... -120,00 EUR\n\nTOTAL A PAGAR: 848,00 EUR",
    },
    {
      name: "English invoice in US dollars",
      body: "INVOICE\nInvoice number: INV-3381\nDate: March 3, 2026\n\nFrom: Northwind Example LLC\nTax ID: 98-7654321\n\nBill to: Contoso Demo Inc.\n\nConsulting, 12 hours @ 150.00 USD ... 1,800.00 USD\nSales tax (8%) ....................... 144.00 USD\n\nTotal due: 1,944.00 USD",
    },
  ],
};
