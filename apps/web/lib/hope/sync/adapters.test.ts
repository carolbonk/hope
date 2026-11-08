import { flushDecisions, mirrorDecision } from "./decisions";
import { fetchOpportunities } from "./opportunities";
import { loadRemoteProfile, saveRemoteProfile } from "./profile";
import { emptyProfile } from "../store";

it("H0 adapters are no-ops that never throw or reject", async () => {
  await expect(loadRemoteProfile()).resolves.toBeNull();
  expect(saveRemoteProfile(emptyProfile())).toBeUndefined();
  await expect(fetchOpportunities()).resolves.toBeNull();
  expect(mirrorDecision("opp-1", "saved")).toBeUndefined();
  await expect(flushDecisions()).resolves.toBeUndefined();
});
