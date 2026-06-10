import { describe, it, expect } from "vitest";

// Mock helper function representing the rendering title selection logic in page.tsx
export function getTitleText(kind: string, cost: number): string {
  let titleText = "Conflit Co-accepté";
  if (kind === "inference") {
    if (cost === 5.0) titleText = "Inférence DÉDUCTIVE violée";
    else if (cost === 2.0) titleText = "Inférence défaisable fort violée";
    else if (cost === 1.0) titleText = "Inférence défaisable faible violée";
    else titleText = `Inférence violée (coût ${cost})`;
  }
  return titleText;
}

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
