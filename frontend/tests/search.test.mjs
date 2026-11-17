import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { matchesText, searchPattern } from "../src/utils/search.ts";
import { highlight } from "../src/utils/format.ts";

const cases = JSON.parse(readFileSync(new URL("../../tests/search-cases.json", import.meta.url), "utf8"));

for (const { term, text, whole } of cases) {
  test(`${JSON.stringify(term)} in ${JSON.stringify(text)}`, () => {
    assert.equal(matchesText(text, term), whole);
    assert.equal(matchesText(text, term, true), true);
    assert.equal([...text.matchAll(searchPattern(term))].length > 0, whole);
    assert.equal(highlight(text, term).includes("<mark>"), whole);
    assert.equal(highlight(text, term, true).includes("<mark>"), true);
  });
}

test("title highlighting escapes HTML without searching HTML entities", () => {
  assert.equal(highlight("<ECR>", "ecr"), "&lt;<mark>ECR</mark>&gt;");
  assert.equal(highlight("&", "amp"), "&amp;");
  assert.equal(highlight("<script>", "<script>"), "<mark>&lt;script&gt;</mark>");
});

test("highlight offsets preserve original text and mode", () => {
  const text = "配置ECR仓库 secret ECR";
  assert.deepEqual([...text.matchAll(searchPattern("ecr"))].map(m => m.index), [2, 15]);
  assert.deepEqual([...text.matchAll(searchPattern("ecr", true))].map(m => m.index), [2, 9, 15]);
});
