const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("static/js/owner.js", "utf8");
const normalizer = source.slice(source.indexOf("function normalizeSearch("), source.indexOf("function initTabs("));
const matcher = source.slice(source.indexOf("function keywordMatchDetails("), source.indexOf("function initKeywordPatternAnalyzer("));
const context = vm.createContext({});
vm.runInContext(normalizer + matcher, context);

test("ed does not match unrelated patterns, assignment names or wrong choices", () => {
  const item = {prompt: "She usually ___ to school", correct_answer: "A. goes", options_text: "goes went played", assignment_title: "Quá khứ", patterns: ["Đuôi -ed"]};
  assert.equal(context.questionMatchesKeyword(item, "ed"), false);
  assert.equal(context.questionMatchesKeyword({prompt: "I need a seed", correct_answer: "need"}, "ed"), false);
});

test("ed matches and explains a suffix in the question or correct answer", () => {
  const item = {prompt: "Yesterday I ___ football", correct_answer: "B. played"};
  assert.equal(context.questionMatchesKeyword(item, "-ed"), true);
  assert.equal(Array.from(context.keywordMatchDetails(item, "ed"))[0], "Đáp án đúng: played");
  assert.equal(context.questionMatchesKeyword({prompt: "Pronounce -ed"}, "ed"), true);
});

test("ordinary search respects word boundaries and shows matching source", () => {
  const item = {prompt: "They played yesterday", options_text: "go goes gone", explanation: "Thì quá khứ"};
  assert.equal(context.questionMatchesKeyword(item, "day"), false);
  assert.equal(context.questionMatchesKeyword(item, "go"), true);
  assert.deepEqual(Array.from(context.keywordMatchDetails(item, "qua khu")), ["Giải thích"]);
  assert.equal(context.questionMatchesKeyword({assignment_title: "Quá khứ", patterns: ["Yesterday"]}, "yesterday"), false);
});
