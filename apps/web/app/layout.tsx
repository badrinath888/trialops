import type { ReactNode } from "react";
import "./globals.css";
export const metadata = {
  title: {
    default: "TrialOps — from issue to evidence",
    template: "%s · TrialOps",
  },
  description:
    "An evidence-first workspace for clinical operations support. Investigate issues, review procedures, and track human decisions.",
};
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#main-content">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
