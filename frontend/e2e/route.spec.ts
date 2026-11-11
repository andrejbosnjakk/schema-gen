// The edge router never yields a path with NaN, for any two card positions (two cards stacked in one column, in one row, on top of each other, ...).
import { expect, test } from "@playwright/test";
import { CH, CW, ends, rounded, route } from "../src/diagram/layout";

test("route and rounded give finite paths for every relative position of two cards", () => {
  const xs = [-2 * CW, -CW - 28, -CW, -CW + 10, -10, 0, 10, CW - 10, CW, CW + 20, CW + 28, 2 * CW + 56], ys = [-3 * CH, -CH - 6, -CH, -1, 0, 1, CH, CH + 6, 3 * CH];
  let n = 0;
  for (const dx of xs) for (const dy of ys) {
    const d = rounded(ends({ x: 100, y: 100 }, { x: 100 + dx, y: 100 + dy }));
    expect(d, `dx ${dx} dy ${dy}`).not.toMatch(/NaN|Infinity/); n++;
  }
  expect(rounded(route(0, 5, 0, 5))).not.toMatch(/NaN/);
  expect(n).toBe(xs.length * ys.length);
});
