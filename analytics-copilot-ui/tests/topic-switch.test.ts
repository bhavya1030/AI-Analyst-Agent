/**
 * Frontend topic-switch: GDP → IPL must drop file_path.
 */

import {
  contentTokens,
  isTopicSwitch,
  shouldOmitFilePath,
} from "@/utils/topicSwitch";

describe("topic switch GDP → IPL → Gold → Population", () => {
  const gdpPath = "/data/local_library/india_gdp.csv";
  const gdpName = "india_gdp.csv";

  it("extracts content tokens", () => {
    const t = contentTokens("Analyze IPL stats for 2024");
    expect(t.has("ipl")).toBe(true);
    expect(t.has("analyze")).toBe(false);
  });

  it("GDP bound + Analyze IPL → switch and omit path", () => {
    expect(isTopicSwitch("Analyze IPL", gdpName, gdpPath)).toBe(true);
    expect(shouldOmitFilePath("Analyze IPL", gdpName, gdpPath)).toBe(true);
  });

  it("GDP bound + show histogram → keep file", () => {
    expect(isTopicSwitch("Show histogram", gdpName, gdpPath)).toBe(false);
    expect(shouldOmitFilePath("Show histogram", gdpName, gdpPath)).toBe(false);
  });

  it("GDP bound + Analyze India GDP → keep file", () => {
    expect(isTopicSwitch("Analyze India GDP trends", gdpName, gdpPath)).toBe(
      false
    );
  });

  it("full transition chain", () => {
    const chain: Array<[string, string, string, boolean]> = [
      ["India GDP", gdpPath, "Analyze IPL", true],
      ["IPL matches", "/data/ipl_stats.csv", "Analyze gold prices", true],
      ["Gold prices", "/data/gold_prices.csv", "Analyze world population", true],
      ["Population", "/data/population.csv", "Analyze India GDP", true],
      ["India GDP", gdpPath, "Forecast next 5 years", false],
      ["India GDP", gdpPath, "Show correlation", false],
    ];
    for (const [name, path, q, exp] of chain) {
      expect(isTopicSwitch(q, name, path)).toBe(exp);
    }
  });

  it("uploaded ipl file + Analyze IPL keeps path", () => {
    expect(
      isTopicSwitch("Analyze IPL", "ipl_stats.csv", "/tmp/ipl_stats.csv")
    ).toBe(false);
  });
});
