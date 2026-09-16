/**
 * Pin the timezone for the whole mobile test run.
 *
 * Every day-based helper in `lib/local-day.ts` reads the ambient zone, so a
 * suite that inherits the machine's zone tests a different thing on a laptop in
 * New York than on a CI runner in UTC. UTC never shifts its clocks, which is
 * the worst case: a daylight-saving bug passes CI and appears only on a phone.
 *
 * Jest ignores `process.env.TZ` set inside a test file, because the runtime has
 * already cached the zone by then. Setting it here works because Jest forks its
 * workers after global setup, and a worker inherits this environment.
 *
 * America/New_York is chosen because it shifts its clocks twice a year at
 * 02:00. Its transitions are what `__tests__/local-day-dst.test.ts` asserts
 * against.
 */
module.exports = () => {
  process.env.TZ = "America/New_York";
};
