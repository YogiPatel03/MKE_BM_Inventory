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
const typesSource = await read("src/types/index.ts");
const itemModalSource = await read("src/components/modals/ItemModal.tsx");
const itemDetailSource = await read("src/pages/ItemDetailPage.tsx");
const cabinetDetailSource = await read("src/pages/CabinetDetailPage.tsx");
const inventoryListSource = await read("src/pages/InventoryListPage.tsx");
const inventorySearchSource = await read("src/pages/InventoryPage.tsx");
const clientSource = await read("src/api/client.ts");

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
