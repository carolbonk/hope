import { readFileSync } from "node:fs";
import { join } from "node:path";

const MOCKS = join(__dirname, "..", "..", "..", "..", "..", "contracts", "mocks", "w1");

/** A `contracts/mocks/w1/<name>.json` mock as a fetch `Response`. */
export function w1(name: string): Response {
  const mock = JSON.parse(readFileSync(join(MOCKS, `${name}.json`), "utf8")) as {
    status: number;
    headers: Record<string, string>;
    body: unknown;
  };
  const body = mock.body === null ? null : JSON.stringify(mock.body);
  return new Response(body, { status: mock.status, headers: { "content-type": "application/json", ...mock.headers } });
}
