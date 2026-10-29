import type { Metadata } from "next";
import "./globals.scss";

export const metadata: Metadata = {
  title: "AETHER | Industrial Intelligence",
  description: "Operational intelligence for industrial systems.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
