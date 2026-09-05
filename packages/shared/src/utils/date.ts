import type { TimeRange } from '../constants';
import { TIME_RANGES } from '../constants';

export function formatDate(
  dateString: string | null | undefined,
  fallback: string = 'Never',
  locale: string = 'en-AU',
): string {
  if (!dateString) return fallback;
  try {
    return new Date(dateString).toLocaleDateString(locale, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  } catch {
    return dateString;
  }
}

export function formatShortDate(
  dateString: string | null | undefined,
  fallback: string = 'Never',
  locale: string = 'en-AU',
): string {
  if (!dateString) return fallback;
  try {
    return new Date(dateString).toLocaleDateString(locale, { month: 'short', day: 'numeric' });
  } catch {
    return dateString;
  }
}

export function formatTime(
  dateString: string | null | undefined,
  fallback: string = 'Never',
  locale: string = 'en-AU',
): string {
  if (!dateString) return fallback;
  try {
    return new Date(dateString).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch {
    return dateString;
  }
}

export function formatDateTime(
  dateString: string | null | undefined,
  fallback: string = 'Never',
  locale: string = 'en-AU',
): string {
  if (!dateString) return fallback;
  try {
    return new Date(dateString).toLocaleDateString(locale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateString;
  }
}

export interface DateRange {
  start_date: string | undefined;
  end_date: string | undefined;
}

export function getDateRange(timeRange: TimeRange): DateRange {
  if (timeRange === 'ALL') return { start_date: undefined, end_date: undefined };
  const range = TIME_RANGES.find((r) => r.label === timeRange);
  if (!range?.months) return { start_date: undefined, end_date: undefined };
  const endDate = new Date();
  const startDate = new Date();
  startDate.setMonth(startDate.getMonth() - range.months);
  return { start_date: startDate.toISOString().split('T')[0], end_date: endDate.toISOString().split('T')[0] };
}

export function formatSyncAge(dateString: string | null | undefined): string | null {
  if (!dateString) return null;
  const diff = Date.now() - new Date(dateString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function parseDateString(dateString: string): Date | undefined {
  if (!dateString) return undefined;
  const [year, month, day] = dateString.split('-').map(Number);
  if (!year || !month || !day) return undefined;
  return new Date(year, month - 1, day);
}

export function formatDateToString(date: Date | undefined): string {
  if (!date) return '';
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
