import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import ts from "typescript";

const root = resolve(import.meta.dirname, "..");

async function read(relativePath) {
  return readFile(resolve(root, relativePath), "utf8");
}

async function importTs(relativePath) {
  const source = await read(relativePath);
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2020,
      target: ts.ScriptTarget.ES2020,
      strict: true,
    },
    fileName: relativePath,
  });
  const encoded = Buffer.from(compiled.outputText, "utf8").toString("base64");
  return import(`data:text/javascript;base64,${encoded}`);
}

function test(name, fn) {
  try {
    fn();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

const itemPayloads = await importTs("src/api/itemPayloads.ts");
const checklistDateHelpers = await importTs("src/utils/checklistDateHelpers.ts");
const { formatSabhaDate, parseLocalDate } = checklistDateHelpers;
const typesSource = await read("src/types/index.ts");
const itemModalSource = await read("src/components/modals/ItemModal.tsx");
const itemDetailSource = await read("src/pages/ItemDetailPage.tsx");
const cabinetDetailSource = await read("src/pages/CabinetDetailPage.tsx");
const inventoryListSource = await read("src/pages/InventoryListPage.tsx");
const inventorySearchSource = await read("src/pages/InventoryPage.tsx");
const clientSource = await read("src/api/client.ts");

// ── formatSabhaDate / parseLocalDate ─────────────────────────────────────────

test("formatSabhaDate: valid sabhaDate returns formatted date", () => {
  const result = formatSabhaDate("2026-05-10");
  assert.equal(result, "May 10, 2026");
});

test("formatSabhaDate: missing sabhaDate falls back to weekStart", () => {
  const result = formatSabhaDate(null, "2026-05-03");
  assert.equal(result, "Week of May 3, 2026");
});

test("formatSabhaDate: undefined sabhaDate falls back to weekStart", () => {
  const result = formatSabhaDate(undefined, "2026-05-03");
  assert.equal(result, "Week of May 3, 2026");
});

test("formatSabhaDate: malformed sabhaDate falls back to weekStart", () => {
  const result = formatSabhaDate("abc-def-ghi", "2026-05-03");
  assert.equal(result, "Week of May 3, 2026");
});

test("formatSabhaDate: impossible date falls back to weekStart", () => {
  const result = formatSabhaDate("2026-99-99", "2026-05-03");
  assert.equal(result, "Week of May 3, 2026");
});

test("formatSabhaDate: both missing returns unavailable string", () => {
  const result = formatSabhaDate(null, null);
  assert.equal(result, "Sabha date unavailable");
});

test("formatSabhaDate: both undefined returns unavailable string", () => {
  const result = formatSabhaDate(undefined, undefined);
  assert.equal(result, "Sabha date unavailable");
});

test("formatSabhaDate: malformed sabhaDate and missing weekStart returns unavailable string", () => {
  const result = formatSabhaDate("not-a-date");
  assert.equal(result, "Sabha date unavailable");
});

test("parseLocalDate: returns null for wrong part count", () => {
  assert.equal(parseLocalDate("2026-05"), null);
  assert.equal(parseLocalDate("2026"), null);
});

test("parseLocalDate: returns null for non-numeric parts", () => {
  assert.equal(parseLocalDate("abc-def-ghi"), null);
});

test("parseLocalDate: returns null for overflowed date", () => {
  assert.equal(parseLocalDate("2026-13-01"), null);
  assert.equal(parseLocalDate("2026-01-32"), null);
});

test("parseLocalDate: valid date returns Date with correct local components", () => {
  const d = parseLocalDate("2026-05-10");
  assert.notEqual(d, null);
  assert.equal(d.getFullYear(), 2026);
  assert.equal(d.getMonth(), 4); // 0-indexed
  assert.equal(d.getDate(), 10);
});

// ── Item type tests ───────────────────────────────────────────────────────────

test("Item type includes requiresRequest", () => {
  assert.match(typesSource, /requiresRequest: boolean;/);
});

test("response client maps requires_request to requiresRequest", () => {
  assert.match(clientSource, /camelcaseKeys\(r\.data,\s*\{\s*deep:\s*true\s*\}\)/);
});

test("create payload maps requiresRequest to requires_request with false default", () => {
  assert.equal(
    itemPayloads.toItemCreateApiPayload({
      name: "Extension cord",
      quantityTotal: 1,
      cabinetId: 2,
      sku: "EXT1",
    }).requires_request,
    false
  );
  assert.equal(
    itemPayloads.toItemCreateApiPayload({
      name: "Extension cord",
      quantityTotal: 1,
      cabinetId: 2,
      sku: "EXT1",
      requiresRequest: true,
    }).requires_request,
    true
  );
});

test("update payload maps requiresRequest and preserves explicit false", () => {
  const payload = itemPayloads.toItemUpdateApiPayload({ requiresRequest: false });
  assert.equal(Object.hasOwn(payload, "requires_request"), true);
  assert.equal(payload.requires_request, false);
});

test("create and edit UI expose item request setting with false default", () => {
  assert.match(itemModalSource, /const \[requiresRequest, setRequiresRequest\] = useState\(false\)/);
  assert.match(itemModalSource, /Item needs to be requested/);
  assert.match(itemModalSource, /When enabled, users must request this item instead of checking it out directly\./);
  assert.match(itemDetailSource, /Item needs to be requested/);
  assert.match(itemDetailSource, /setRequiresRequest\(e\.target\.checked\)/);
  assert.match(itemDetailSource, /canManage && \(/);
  assert.match(cabinetDetailSource, /canManage && \(/);
});

test("request-required badge appears in display surfaces", () => {
  for (const source of [itemDetailSource, cabinetDetailSource, inventoryListSource, inventorySearchSource]) {
    assert.match(source, /Request required/);
  }
});

test("checkout UI applies requiresRequest after full-bin rule", () => {
  assert.match(itemDetailSource, /This item must be requested before checkout\./);
  assert.match(itemDetailSource, /item\.requiresRequest \? "Request item" : "Request checkout"/);
  assert.match(cabinetDetailSource, /!requiresFullBinCheckout && mustRequest/);
  assert.match(cabinetDetailSource, /Request item/);
  assert.match(cabinetDetailSource, /Full bin only/);
  assert.match(cabinetDetailSource, /user\?\.role\.name === "ADMIN" \|\| user\?\.role\.name === "COORDINATOR"/);
});
