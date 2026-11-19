import { demoOpportunities } from "./demo";
import { applicability, oppDocs } from "./dossier";
import { emptyProfile } from "./store";
import type { OrgProfile } from "./types";

const profile = (over: Partial<OrgProfile> = {}): OrgProfile => ({
  ...emptyProfile(),
  ...over,
});
const opps = demoOpportunities(new Date("2026-11-07T12:00:00"));
const opp = (id: string) => opps.find((o) => o.id === id)!;
const level = (
  id: Parameters<typeof applicability>[0],
  p: OrgProfile,
  o?: Parameters<typeof applicability>[2],
) => applicability(id, p, o).level;

describe("applicability", () => {
  it("US-only items need a country, apply in the US and not elsewhere", () => {
    expect(level("ein_letter", profile())).toBe("needs_info");
    expect(level("ein_letter", profile({ country: "US" }))).toBe("usual");
    expect(level("ein_letter", profile({ country: "MX" }))).toBe("auto_na");
    expect(level("good_standing", profile({ country: "MX" }))).toBe(
      "when_asked",
    );
  });

  it("501(c)(3) letter follows the US status answer", () => {
    expect(
      level("irs_501c3", profile({ country: "US", has501c3: "yes" })),
    ).toBe("usual");
    expect(level("irs_501c3", profile({ country: "US", has501c3: "no" }))).toBe(
      "auto_na",
    );
    expect(level("irs_501c3", profile({ country: "US" }))).toBe("needs_info");
    expect(level("irs_501c3", profile({ country: "MX" }))).toBe("auto_na");
  });

  it("W-9 applies only when a call asks, and needs US tax info outside the US", () => {
    const asks = opp("opp-county-schools");
    expect(level("w9", profile({ country: "US", legalStatus: "501c3" }))).toBe(
      "when_asked",
    );
    expect(
      level("w9", profile({ country: "US", legalStatus: "501c3" }), asks),
    ).toBe("usual");
    expect(
      level(
        "w9",
        profile({ country: "US", legalStatus: "fiscal_sponsor" }),
        asks,
      ),
    ).toBe("needs_info");
    expect(level("w9", profile(), asks)).toBe("needs_info");
    expect(level("w9", profile({ country: "MX" }), asks)).toBe("needs_info");
    expect(
      level("w9", profile({ country: "MX", usTaxStatus: "yes" }), asks),
    ).toBe("usual");
    expect(
      level("w9", profile({ country: "MX", usTaxStatus: "no" }), asks),
    ).toBe("auto_na");
  });

  it("UEI and SAM apply to federal calls only", () => {
    for (const id of ["uei", "sam"] as const) {
      expect(level(id, profile({ country: "US" }))).toBe("when_asked");
      expect(
        level(id, profile({ country: "US" }), opp("opp-county-schools")),
      ).toBe("usual");
      expect(
        level(id, profile({ country: "US" }), opp("opp-sunrise-ops")),
      ).toBe("when_asked");
    }
  });

  it("child protection follows whether the org serves minors", () => {
    expect(level("child_protection", profile({ servesMinors: "yes" }))).toBe(
      "usual",
    );
    expect(level("child_protection", profile({ servesMinors: "no" }))).toBe(
      "auto_na",
    );
    expect(level("child_protection", profile())).toBe("needs_info");
  });
});

describe("oppDocs", () => {
  it("lists the call's documents plus UEI/SAM for federal calls, with their dossier status", () => {
    const p = profile({
      country: "US",
      servesMinors: "yes",
      dossier: {
        w9: {
          status: "declared",
          naReason: "",
          evidenceRef: "w9.pdf",
          period: "",
          expires: "",
          comments: [],
        },
        child_protection: {
          status: "declared",
          naReason: "",
          evidenceRef: "policy.pdf",
          period: "",
          expires: "2020-01-01",
          comments: [],
        },
        sam: {
          status: "not_applicable",
          naReason: "local contract",
          evidenceRef: "",
          period: "",
          expires: "",
          comments: [],
        },
      },
    });
    const docs = Object.fromEntries(
      oppDocs(opp("opp-county-schools"), p).map((d) => [d.id, d]),
    );
    expect(Object.keys(docs).sort()).toEqual([
      "child_protection",
      "sam",
      "uei",
      "w9",
    ]);
    expect(docs.w9).toMatchObject({ status: "declared", expired: false });
    expect(docs.child_protection).toMatchObject({
      status: "declared",
      expired: true,
    });
    expect(docs.sam).toMatchObject({
      status: "not_applicable",
      expired: false,
    });
    expect(docs.uei).toMatchObject({ status: "pending", level: "usual" });
  });

  it("a call with no documents lists none", () => {
    expect(oppDocs(opp("opp-lumen-arts"), profile())).toEqual([]);
  });
});
