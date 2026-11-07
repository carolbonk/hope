import { FIXED_NOW } from "@/test/render";
import { ApiError, StaleArtifactError } from "./errors";
import { FixtureApi } from "./fixture";
import { FIXTURE_SESSION } from "./fixtures/workflows";

const fresh = () => new FixtureApi({ now: () => FIXED_NOW });

describe("FixtureApi", () => {
  it("ranks the matrix by composite score", async () => {
    const { rows } = await fresh().getMatrix("a");
    expect(rows.map((r) => r.rank)).toEqual(rows.map((_, i) => i + 1));
    expect(rows.every((r, i) => i === 0 || (rows[i - 1]?.composite_score ?? 0) >= r.composite_score)).toBe(true);
    expect(rows.find((r) => r.eligibility === "ineligible")?.composite_score).toBe(0);
  });

  it("only returns requests for the given roles", async () => {
    const api = fresh();
    const mine = await api.listHitlRequests(FIXTURE_SESSION.roles);
    expect(mine.some((r) => r.approver_roles.includes("board_chair"))).toBe(false);
    expect(await api.listHitlRequests(["board_chair"])).toHaveLength(1);
  });

  it("rejects a stale hash with 409, then accepts the refreshed one", async () => {
    const api = fresh();
    const req = (await api.listHitlRequests(["finance_director"])).find((r) => r.gate === "HITL-2")!;
    const body = { decision: "approve" as const, artifact_hash: req.artifact_hash, comment: null };
    await expect(api.submitSignal(req.workflow_id, "HITL-2", body, { stepUpToken: "t" })).rejects.toBeInstanceOf(StaleArtifactError);
    const refreshed = (await api.listHitlRequests(["finance_director"])).find((r) => r.gate === "HITL-2")!;
    expect(refreshed.artifact_hash).not.toBe(req.artifact_hash);
    await api.submitSignal(req.workflow_id, "HITL-2", { ...body, artifact_hash: refreshed.artifact_hash }, { stepUpToken: "t" });
    expect((await api.getWorkflow(req.workflow_id)).state).toBe("Drafting");
  });

  it("requires step-up for HITL-5", async () => {
    const api = fresh();
    const req = (await api.listHitlRequests(["aor"]))[0]!;
    await expect(
      api.submitSignal(req.workflow_id, req.gate, { decision: "approve", artifact_hash: req.artifact_hash, comment: null }),
    ).rejects.toMatchObject({ status: 401 } satisfies Partial<ApiError>);
  });

  it("turns protected profile edits into HITL-0 proposals and applies them on approval", async () => {
    const api = fresh();
    const { profile, etag } = await api.getProfile();
    const res = await api.patchProfile("a", { legal: { ...profile.legal, legal_name: "Riverbend Health Alliance" } }, etag);
    expect(res.status).toBe("pending_approval");
    expect((await api.getProfile()).profile.legal.legal_name).toBe(profile.legal.legal_name);
    const req = (await api.listHitlRequests(["finance_director"])).find((r) => r.gate === "HITL-0")!;
    await api.submitSignal(req.workflow_id, "HITL-0", { decision: "approve", artifact_hash: req.artifact_hash, comment: null });
    expect((await api.getProfile()).profile.legal.legal_name).toBe("Riverbend Health Alliance");
  });

  it("applies unprotected edits immediately and enforces the ETag", async () => {
    const api = fresh();
    const { profile, etag } = await api.getProfile();
    const res = await api.patchProfile("a", { mission: { ...profile.mission, focus_areas: ["Oral health"] } }, etag);
    expect(res.status).toBe("applied");
    await expect(api.patchProfile("a", { mission: profile.mission }, etag)).rejects.toMatchObject({ status: 412 });
  });
});
