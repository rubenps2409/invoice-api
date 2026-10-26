// Display helpers. The API sends money as decimal strings ("1210.00"); these only format
// them for the eye, nothing is calculated here.

export function money(amount, currency) {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      currencyDisplay: "code",
    })
      .format(amount)
      .replace(/ /g, " ");
  } catch {
    return `${amount} ${currency}`;
  }
}

// A model call costs fractions of a cent, so keep the significant decimals: 0.00034 -> $0.00034.
export function usd(amount) {
  const value = Number(amount);
  if (!Number.isFinite(value) || value === 0) return "$0.00";
  const text = value.toFixed(5).replace(/0+$/, "");
  const [whole, decimals = ""] = text.split(".");
  return `$${whole}.${decimals.padEnd(2, "0")}`;
}

export function isoDate(iso) {
  if (!iso) return "";
  const date = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeZone: "UTC" }).format(date);
}

// Withholding is subtracted from the total, so it is shown with the opposite sign.
export function negate(amount) {
  const value = String(amount);
  if (Number(value) === 0) return value;
  return value.startsWith("-") ? value.slice(1) : `-${value}`;
}

export function isZero(amount) {
  return Number(amount) === 0;
}

export function waitText(seconds) {
  const s = Math.max(1, Math.ceil(seconds));
  if (s < 60) return `${s} s`;
  const minutes = Math.ceil(s / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}
