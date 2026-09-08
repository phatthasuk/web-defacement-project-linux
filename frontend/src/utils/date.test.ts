import { describe, it, expect } from 'vitest';
import { parseDate, formatDateTime } from './date';

describe('date utils', () => {
  it('parses naive ISO string as UTC', () => {
    const naive = '2026-09-03T07:35:12.414864';
    const parsed = parseDate(naive);
    expect(parsed.getUTCFullYear()).toBe(2026);
    expect(parsed.getUTCMonth()).toBe(8); // 0-indexed: 8 is September
    expect(parsed.getUTCDate()).toBe(3);
    expect(parsed.getUTCHours()).toBe(7);
    expect(parsed.getUTCMinutes()).toBe(35);
    expect(parsed.getUTCSeconds()).toBe(12);
  });

  it('parses ISO string with trailing Z as UTC', () => {
    const withZ = '2026-09-03T07:35:12.414864Z';
    const parsed = parseDate(withZ);
    expect(parsed.getUTCHours()).toBe(7);
    expect(parsed.getUTCMinutes()).toBe(35);
  });

  it('parses ISO string with offset correctly', () => {
    const withOffset = '2026-09-03T14:35:12+07:00';
    const parsed = parseDate(withOffset);
    expect(parsed.getUTCHours()).toBe(7);
    expect(parsed.getUTCMinutes()).toBe(35);
  });

  it('formats invalid or missing dates gracefully', () => {
    expect(formatDateTime(undefined)).toBe('N/A');
    expect(formatDateTime(null)).toBe('N/A');
    expect(formatDateTime('')).toBe('N/A');
  });

  it('formats valid dates to non-empty string', () => {
    const formatted = formatDateTime('2026-09-03T07:35:12.414864');
    expect(formatted).toBeTruthy();
    expect(formatted).not.toBe('N/A');
  });
});
