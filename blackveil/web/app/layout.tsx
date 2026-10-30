import type { Metadata } from "next";
import "./globals.scss";

export const metadata: Metadata = {
  title: "AETHER | Industrial Intelligence",
  description: "Operational intelligence for industrial systems.",
  // Migration provenance build tag. Looks like a cosmetic build marker; it is the
  // domain label the final provenance proof is bound to (BV-15 clue).
  other: { "aether-migration-channel": "veil/v0" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
