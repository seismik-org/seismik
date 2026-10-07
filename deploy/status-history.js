// Preserve the existing Cloudflare D1 probes table; missing minutes are unknown.
const SERVICES = ["api", "web", "developers"];

export async function recordProbe(db, status, timestamp = Date.now()) {
  if (!db) throw new Error("STATUS_DB binding is missing");
  const minute = Math.floor(timestamp / 60_000);
  await db.prepare("INSERT OR IGNORE INTO probes (minute, api, web, developers) VALUES (?, ?, ?, ?)")
    .bind(minute, ...SERVICES.map(name => Number(status.services[name]))).run();
}

export async function readHistory(db, timestamp = Date.now()) {
  if (!db) return { available: false, days: [] };
  const today = Math.floor(timestamp / 86_400_000);
  const firstDay = today - 29;
  const { results } = await db.prepare(`SELECT CAST(minute / 1440 AS INTEGER) AS day,
    COUNT(*) AS samples, SUM(api) AS api, SUM(web) AS web, SUM(developers) AS developers
    FROM probes WHERE minute >= ? AND minute <= ? GROUP BY day ORDER BY day`)
    .bind(firstDay * 1440, Math.floor(timestamp / 60_000)).all();
  const byDay = new Map(results.map(row => [Number(row.day), row]));
  return { available: true, days: Array.from({ length: 30 }, (_, offset) => {
    const day = firstDay + offset;
    const row = byDay.get(day);
    return { date: new Date(day * 86_400_000).toISOString().slice(0, 10),
      samples: Number(row?.samples ?? 0),
      services: Object.fromEntries(SERVICES.map(name => [name, {
        healthy: Number(row?.[name] ?? 0), failed: Number(row?.samples ?? 0) - Number(row?.[name] ?? 0),
      }])) };
  }) };
}
