import { RequireSession } from "@/lib/api/session/RequireSession";
import { HopeFooter, HopeNav } from "@/components/hope/ui";
import { HopeSync } from "@/lib/hope/sync";


export const metadata = { title: "Hope — find your next possibility (demo)" };

export default function HopeLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="-mt-8 sm:-mt-10">
      <HopeNav />
      <HopeSync />
      <RequireSession>{children}</RequireSession>
      <HopeFooter />
    </div>
  );
}
