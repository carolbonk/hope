import { HopeFooter, HopeNav } from "@/components/hope/ui";


export const metadata = { title: "Hope — find your next possibility (demo)" };

export default function HopeLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="-mt-8 sm:-mt-10">
      <HopeNav />
      {children}
      <HopeFooter />
    </div>
  );
}
