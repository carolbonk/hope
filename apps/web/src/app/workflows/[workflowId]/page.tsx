import { WorkflowDetail } from "@/features/workflow/WorkflowScreen";

export default async function WorkflowPage({ params }: { params: Promise<{ workflowId: string }> }) {
  const { workflowId } = await params;
  return <WorkflowDetail workflowId={decodeURIComponent(workflowId)} />;
}
