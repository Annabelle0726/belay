const assert = require("node:assert/strict");
const test = require("node:test");
require("../control-messages.js");

test("learner sees a useful limit message without private usage", () => {
  assert.match(globalThis.belayControlMessage({code: "budget_exhausted", class_usage: "PRIVATE"}), /usage limit/);
  assert.doesNotMatch(globalThis.belayControlMessage({code: "budget_exhausted", class_usage: "PRIVATE"}), /PRIVATE/);
});
test("retry timing is bounded and untrusted errors stay hidden", () => {
  assert.match(globalThis.belayControlMessage({code: "rate_limited"}, "3"), /3 seconds/);
  assert.doesNotMatch(globalThis.belayControlMessage({code: "rate_limited"}, "<script>"), /script/);
  assert.doesNotMatch(globalThis.belayControlMessage({code: "provider-secret"}), /provider-secret/);
});
