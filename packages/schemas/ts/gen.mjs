// Generates src/index.ts from ../json/bundle.schema.json (itself exported from hope_core).
import { readFileSync, writeFileSync } from "node:fs";
import { compile } from "json-schema-to-typescript";

const bundle = JSON.parse(readFileSync(new URL("../json/bundle.schema.json", import.meta.url)));
// Pydantic titles every field; drop those so TS gets inline types, not one alias per field.
const stripFieldTitles = (node) => {
  if (Array.isArray(node)) return node.forEach(stripFieldTitles);
  if (!node || typeof node !== "object") return;
  for (const child of Object.values(node.properties ?? {})) delete child.title;
  Object.values(node).forEach(stripFieldTitles);
};
stripFieldTitles(bundle);

const ts = await compile(bundle, "HopeContracts", {
  bannerComment:
    "/* Generated from packages/schemas/json/bundle.schema.json. Do not edit; run `pnpm --filter @hope/schemas gen`. */",
  unreachableDefinitions: true,
  additionalProperties: false,
  strictIndexSignatures: true,
  format: true,
});
writeFileSync(new URL("./src/index.ts", import.meta.url), ts);
console.log("wrote src/index.ts");
