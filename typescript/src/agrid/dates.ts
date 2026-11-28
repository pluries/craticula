import { CompileError } from "../errors.js";

/**
 * SEM-4: dates and zones, resolved without the host's time zone or locale. Civil dates are handled as UTC midnights of the calendar
 * date; an IANA zone is applied through `Intl` only to find the local date of an instant and the offset of a local wall-clock time.
 */
const ZONE_SHAPE = /^[A-Za-z0-9_+-]+(\/[A-Za-z0-9_+-]+)*$/;
/** tzdata files that load as zones but name whatever zone the server happens to be configured with. */
const NON_ZONES = new Set(["localtime", "factory", "posixrules"]);
const DAY = 86_400_000;
const WIRE_DATE = /^(\d{4})-(\d{2})-(\d{2})(?: (\d{2}):(\d{2}):(\d{2}))?$/;
const INSTANT = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$/;

export const PRESET_NAMES: readonly string[] = [
  "today", "yesterday", "tomorrow", "thisWeek", "lastWeek", "nextWeek", "thisMonth", "lastMonth", "nextMonth", "thisQuarter", "lastQuarter",
  "nextQuarter", "thisYear", "lastYear", "nextYear", "yearToDate", "last7Days", "last30Days", "last90Days", "last6Months", "last12Months", "last24Months",
];

function malformed(message: string): CompileError {
  return new CompileError("InvalidRequest", message, { rejectedAt: "requestParsing", reason: "malformed-request" });
}

const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(zone: string): Intl.DateTimeFormat {
  let found = formatters.get(zone);
  if (found === undefined) {
    found = new Intl.DateTimeFormat("en-US", { timeZone: zone, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", second: "numeric" });
    formatters.set(zone, found);
  }
  return found;
}

/** The zone id if it names an IANA zone this runtime can resolve; otherwise a malformed-request refusal. Never falls back to a default. */
export function resolveZone(id: string): string {
  if (!ZONE_SHAPE.test(id) || NON_ZONES.has(id.toLowerCase())) {
    throw malformed(`'requestContext.zone' must be an IANA time zone id such as 'UTC' or 'Europe/Paris', got '${id}'.`);
  }
  try {
    formatter(id);
  } catch {
    throw malformed(`'requestContext.zone' names a time zone id this host cannot resolve: '${id}' (expected an IANA id such as 'UTC' or 'Europe/Paris').`);
  }
  return id;
}

interface Wall {
  readonly year: number;
  readonly month: number;
  readonly day: number;
  readonly hour: number;
  readonly minute: number;
  readonly second: number;
}

function wallOf(zone: string, instantMs: number): Wall {
  const parts = new Map(formatter(zone).formatToParts(new Date(instantMs)).map((part) => [part.type, Number(part.value)] as const));
  return { year: parts.get("year")!, month: parts.get("month")!, day: parts.get("day")!, hour: parts.get("hour")!, minute: parts.get("minute")!, second: parts.get("second")! };
}

/** The zone's UTC offset at an instant, in milliseconds. */
function offsetMs(zone: string, instantMs: number): number {
  const w = wallOf(zone, instantMs);
  return Date.UTC(w.year, w.month - 1, w.day, w.hour, w.minute, w.second) - Math.floor(instantMs / 1000) * 1000;
}

export function validCalendar(year: number, month: number, day: number): boolean {
  const d = new Date(0);
  d.setUTCFullYear(year, month - 1, day);
  return month >= 1 && month <= 12 && d.getUTCFullYear() === year && d.getUTCMonth() === month - 1 && d.getUTCDate() === day;
}

export function parseWireDate(raw: string): { date: string; time: string | undefined } | undefined {
  const match = WIRE_DATE.exec(raw);
  if (match === null) return undefined;
  const [, y, mo, d, h, mi, s] = match;
  if (!validCalendar(Number(y), Number(mo), Number(d))) return undefined;
  const time = h === undefined ? undefined : `${h}:${mi}:${s}`;
  if (h !== undefined && (Number(h) > 23 || Number(mi) > 59 || Number(s) > 59)) return undefined;
  return { date: `${y}-${mo}-${d}`, time };
}

export interface IsoInstant {
  readonly year: number;
  readonly month: number;
  readonly day: number;
  readonly hour: number;
  readonly minute: number;
  readonly second: number;
  /** The fraction digits as written, without the point (empty when there is none). */
  readonly fraction: string;
  /** The offset from UTC in minutes. */
  readonly offsetMinutes: number;
}

/** An ISO-8601 instant with a date, a time and Z or an offset, or undefined: month 13, `T24:00`, a 60th second and an offset beyond 14 hours are not instants. */
export function parseIsoInstant(raw: string): IsoInstant | undefined {
  const match = INSTANT.exec(raw);
  if (match === null) return undefined;
  const [, y, mo, d, h, mi, s, fraction = "", zone = ""] = match;
  const [year, month, day, hour, minute, second] = [y, mo, d, h, mi, s].map(Number) as [number, number, number, number, number, number];
  if (!validCalendar(year, month, day) || hour > 23 || minute > 59 || second > 59) return undefined;
  let offsetMinutes = 0;
  if (zone !== "Z") {
    const hours = Number(zone.slice(1, 3));
    const minutes = Number(zone.slice(4, 6));
    if (hours > 14 || minutes > 59 || (hours === 14 && minutes !== 0)) return undefined;
    offsetMinutes = (zone.startsWith("-") ? -1 : 1) * (hours * 60 + minutes);
  }
  return { year, month, day, hour, minute, second, fraction, offsetMinutes };
}

/** Whether `raw` is an ISO-8601 instant that is a real instant. */
export function isIsoInstant(raw: string): boolean {
  return parseIsoInstant(raw) !== undefined;
}

/** A local wall-clock time (`YYYY-MM-DD HH:mm:ss`) in a zone as a UTC instant (`...Z`). An ambiguous time takes the later offset; a time that does not exist takes the standard offset. */
export function localDateTimeToInstant(wallClock: string, zone: string): string {
  const parsed = parseWireDate(wallClock);
  if (parsed?.time === undefined) throw malformed(`'${wallClock}' is not a date and time.`);
  const [y, mo, d] = parsed.date.split("-").map(Number) as [number, number, number];
  const [h, mi, s] = parsed.time.split(":").map(Number) as [number, number, number];
  const wall = Date.UTC(y, mo - 1, d, h, mi, s);
  const candidates = [...new Set([offsetMs(zone, wall - DAY), offsetMs(zone, wall + DAY)])];
  const valid = candidates.filter((offset) => offsetMs(zone, wall - offset) === offset);
  const chosen = valid.length > 0 ? Math.max(...valid) : Math.min(...candidates);
  return new Date(wall - chosen).toISOString().replace(".000Z", "Z");
}

function dateText(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

function addMonths(ms: number, months: number): number {
  const d = new Date(ms);
  const index = d.getUTCMonth() + months;
  const year = d.getUTCFullYear() + Math.floor(index / 12);
  const month = ((index % 12) + 12) % 12;
  const last = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return Date.UTC(year, month, Math.min(d.getUTCDate(), last));
}

function localToday(zone: string, now: Date): number {
  const w = wallOf(zone, now.getTime());
  return Date.UTC(w.year, w.month - 1, w.day);
}

/** The half-open civil range `[from, to)` a preset names, in the zone's calendar; undefined when `name` is not a preset. */
export function resolvePreset(name: string, now: Date, zone: string, firstDayOfWeek = 1): { from: string; to: string } | undefined {
  if (!PRESET_NAMES.includes(name)) return undefined;
  const today = localToday(zone, now);
  const tomorrow = today + DAY;
  const dow = new Date(today).getUTCDay();
  const week = today - ((dow - firstDayOfWeek + 7) % 7) * DAY;
  const t = new Date(today);
  const month = Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), 1);
  const quarter = Date.UTC(t.getUTCFullYear(), Math.floor(t.getUTCMonth() / 3) * 3, 1);
  const year = Date.UTC(t.getUTCFullYear(), 0, 1);
  const range = ((): [number, number] => {
    switch (name) {
      case "today": return [today, tomorrow];
      case "yesterday": return [today - DAY, today];
      case "tomorrow": return [tomorrow, today + 2 * DAY];
      case "thisWeek": return [week, week + 7 * DAY];
      case "lastWeek": return [week - 7 * DAY, week];
      case "nextWeek": return [week + 7 * DAY, week + 14 * DAY];
      case "thisMonth": return [month, addMonths(month, 1)];
      case "lastMonth": return [addMonths(month, -1), month];
      case "nextMonth": return [addMonths(month, 1), addMonths(month, 2)];
      case "thisQuarter": return [quarter, addMonths(quarter, 3)];
      case "lastQuarter": return [addMonths(quarter, -3), quarter];
      case "nextQuarter": return [addMonths(quarter, 3), addMonths(quarter, 6)];
      case "thisYear": return [year, addMonths(year, 12)];
      case "lastYear": return [addMonths(year, -12), year];
      case "nextYear": return [addMonths(year, 12), addMonths(year, 24)];
      case "yearToDate": return [year, tomorrow];
      case "last7Days": return [today - 7 * DAY, tomorrow];
      case "last30Days": return [today - 30 * DAY, tomorrow];
      case "last90Days": return [today - 90 * DAY, tomorrow];
      case "last6Months": return [addMonths(today, -6), tomorrow];
      case "last12Months": return [addMonths(today, -12), tomorrow];
      default: return [addMonths(today, -24), tomorrow];
    }
  })();
  return { from: dateText(range[0]), to: dateText(range[1]) };
}
