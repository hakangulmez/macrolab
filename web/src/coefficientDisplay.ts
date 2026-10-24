/** Display annotations only: consume reported estimates, SEs and t intervals.
 * No model result, covariance, confidence interval or export is modified.
 */
import type { JsonRecord } from "./types";

function logGamma(z: number): number {
  const c = [
    676.5203681218851, -1259.1392167224028, 771.3234287776531,
    -176.6150291621406, 12.507343278686905, -0.13857109526572012,
    9.984369578019572e-6, 1.5056327351493116e-7,
  ];
  if (z < 0.5)
    return Math.log(Math.PI / Math.sin(Math.PI * z)) - logGamma(1 - z);
  z -= 1;
  const x = c.reduce((sum, v, i) => sum + v / (z + i + 1), 0.9999999999998099);
  const t = z + 7.5;
  return Math.log(2 * Math.PI) / 2 + (z + 0.5) * Math.log(t) - t + Math.log(x);
}
function betaFraction(a: number, b: number, x: number): number {
  const safe = (v: number) => (Math.abs(v) < 1e-300 ? 1e-300 : v);
  let c = 1,
    d = 1 / safe(1 - ((a + b) * x) / (a + 1)),
    h = d;
  for (let m = 1; m <= 200; m++) {
    for (const aa of [
      (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m)),
      (-(a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1)),
    ]) {
      d = 1 / safe(1 + aa * d);
      c = safe(1 + aa / c);
      h *= d * c;
    }
    if (Math.abs(d * c - 1) < 3e-14) break;
  }
  return h;
}
/** Two-sided Student t tail, used only for displayed significance stars. */
export function tTail(t: number, df: number): number {
  if (t === 0) return 1;
  if (!Number.isFinite(t)) return 0;
  const x = df / (df + t * t),
    a = df / 2,
    b = 0.5;
  if (x === 0) return 0;
  const factor = Math.exp(
    logGamma(a + b) -
      logGamma(a) -
      logGamma(b) +
      a * Math.log(x) +
      b * Math.log1p(-x),
  );
  return x < (a + 1) / (a + b + 2)
    ? (factor * betaFraction(a, b, x)) / a
    : 1 - (factor * betaFraction(b, a, 1 - x)) / b;
}
/** Country OLS does not export its residual df. Recover that integer from the
 * already reported t interval, rather than assuming a full-rank design.
 */
export function reportedDF(
  row: JsonRecord,
  maximum: number,
): number | undefined {
  const se = Number(row.std_error),
    confidence = Number(row.confidence_level);
  const critical = (Number(row.upper) - Number(row.lower)) / (2 * se);
  if (!(
    se > 0 &&
    critical > 0 &&
    confidence > 0 &&
    confidence < 1 &&
    maximum > 0
  ))
    return;
  let low = 1,
    high = Math.floor(maximum);
  while (high - low > 1) {
    const mid = Math.floor((low + high) / 2);
    if (tTail(critical, mid) > 1 - confidence) low = mid;
    else high = mid;
  }
  const df = [low, high].sort(
    (a, b) =>
      Math.abs(tTail(critical, a) - (1 - confidence)) -
      Math.abs(tTail(critical, b) - (1 - confidence)),
  )[0];
  return Math.abs(tTail(critical, df) - (1 - confidence)) < 1e-7
    ? df
    : undefined;
}
export function coefficientStars(row: JsonRecord, df?: number): string {
  const se = Number(row.std_error),
    estimate = Number(row.estimate);
  if (!(se > 0 && Number.isFinite(estimate) && df && df > 0)) return "";
  const p = tTail(estimate / se, df);
  return p < 0.01 ? "***" : p < 0.05 ? "**" : p < 0.1 ? "*" : "";
}
