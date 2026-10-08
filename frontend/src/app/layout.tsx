import type { Metadata } from "next";
import UserBar from "@/components/UserBar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Maintainer Agent",
  description: "Ask questions about a repository's issues, with cited sources.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <UserBar />
        <main>{children}</main>
      </body>
    </html>
  );
}
