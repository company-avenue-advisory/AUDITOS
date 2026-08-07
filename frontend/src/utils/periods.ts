export interface MonthOption {
  label: string;
  value: string;
}

/**
 * Generate the last 24 months as options, most recent first. 24 (not 12) so
 * late GST filings and amendments - commonly needed up to ~20 months after
 * the original period - stay reachable, not just the current filing year.
 */
export function generateMonthOptions(): MonthOption[] {
  const options: MonthOption[] = [];
  const now = new Date();
  for (let i = 0; i < 24; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const year = d.getFullYear();
    const month = d.getMonth() + 1;
    const monthName = d.toLocaleString("en-IN", { month: "long" });
    options.push({
      label: `${monthName} ${year}`,
      value: `${year}-${String(month).padStart(2, "0")}`,
    });
  }
  return options;
}

export const MONTH_OPTIONS: MonthOption[] = generateMonthOptions();

/** Returns the current month in `YYYY-MM` format (most recent option). */
export function currentPeriod(): string {
  return MONTH_OPTIONS[0].value;
}

/** Returns the label for a given period value, or the raw period if not found. */
export function labelForPeriod(period: string): string {
  return MONTH_OPTIONS.find((o) => o.value === period)?.label ?? period;
}
