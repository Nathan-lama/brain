const fs = require('fs');
const path = require('path');

// 1. Mock the describe and it functions
let passed = 0;
let failed = 0;

global.describe = function(name, fn) {
  console.log(`\nSuite: ${name}`);
  fn();
};

global.it = function(name, fn) {
  try {
    fn();
    console.log(`  ✓ PASSED: ${name}`);
    passed++;
  } catch (err) {
    console.error(`  ✗ FAILED: ${name}`);
    console.error(err);
    failed++;
  }
};

global.expect = function(actual) {
  return {
    toBe(expected) {
      if (actual !== expected) {
        throw new Error(`Expected: "${expected}", but got: "${actual}"`);
      }
    }
  };
};

// 2. Define the code to test (extracted from coherence-label.test.tsx)
function getTitleText(kind, cost) {
  let titleText = "Conflit Co-accepté";
  if (kind === "inference") {
    if (cost === 5.0) titleText = "Inférence DÉDUCTIVE violée";
    else if (cost === 2.0) titleText = "Inférence défaisable fort violée";
    else if (cost === 1.0) titleText = "Inférence défaisable faible violée";
    else titleText = `Inférence violée (coût ${cost})`;
  }
  return titleText;
}

// 3. Run the tests
describe("Coherence Label Rendering Logic", () => {
  it("should render 'Inférence DÉDUCTIVE violée' for cost 5.0", () => {
    expect(getTitleText("inference", 5.0)).toBe("Inférence DÉDUCTIVE violée");
  });

  it("should render 'Inférence défaisable fort violée' for cost 2.0", () => {
    expect(getTitleText("inference", 2.0)).toBe("Inférence défaisable fort violée");
  });

  it("should render 'Inférence défaisable faible violée' for cost 1.0", () => {
    expect(getTitleText("inference", 1.0)).toBe("Inférence défaisable faible violée");
  });

  it("should render default conflict title for conflict kinds", () => {
    expect(getTitleText("conflict", 1.0)).toBe("Conflit Co-accepté");
  });
});

console.log(`\nTest results: ${passed} passed, ${failed} failed.\n`);
process.exit(failed > 0 ? 1 : 0);
