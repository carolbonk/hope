import { Suspense } from "react";
import { act, render, screen } from "@testing-library/react";

const GRANT = "3f6b1c2e-9d0a-4e57-8a21-6c5d4b3a2f10";
const workspace = vi.hoisted(() => ({ props: [] as { grantId: string }[] }));
vi.mock("@/components/hope/bids/BidWorkspace", () => ({
  BidWorkspace: (p: { grantId: string }) => {
    workspace.props.push(p);
    return <h1>Workspace {p.grantId}</h1>;
  },
}));

async function renderPage(online: boolean, oppId = GRANT) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_HOPE_API_URL", online ? "http://api.test" : "");
  const { default: BidPage } = await import("./page");
  const params = Promise.resolve({ oppId });
  await act(async () => {
    render(
      <Suspense>
        <BidPage params={params} />
      </Suspense>,
    );
  });
}

beforeEach(() => (workspace.props = []));
afterEach(() => vi.unstubAllEnvs());

it("opens the workspace for the grant in the URL", async () => {
  await renderPage(true, encodeURIComponent(GRANT));
  expect(screen.getByRole("heading", { name: `Workspace ${GRANT}` })).toBeInTheDocument();
  expect(workspace.props.at(-1)).toEqual({ grantId: GRANT });
});

it("says the server is needed when offline", async () => {
  await renderPage(false);
  expect(screen.getByTestId("bids-offline")).toHaveTextContent("My bids needs the Hope server. Sign in to use it.");
  expect(workspace.props).toEqual([]);
});
