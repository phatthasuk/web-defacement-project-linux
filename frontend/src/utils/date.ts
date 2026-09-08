/**
 * Normalizes an ISO date string so that naive UTC strings (without 'Z' or offset)
 * are properly parsed by JavaScript Date as UTC rather than local time.
 */
export function parseDate(isoString: string): Date {
  const normalized = isoString.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(isoString)
    ? isoString
    : `${isoString}Z`;
  return new Date(normalized);
}

/**
 * Formats an ISO date string into a localized date/time string in the user's browser timezone.
 */
export function formatDateTime(
  isoString?: string | null,
  options?: Intl.DateTimeFormatOptions
): string {
  if (!isoString) return 'N/A';
  try {
    return parseDate(isoString).toLocaleString(undefined, options || {
      dateStyle: 'medium',
      timeStyle: 'medium',
    });
  } catch {
    return isoString;
  }
}
