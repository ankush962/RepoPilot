import "./globals.css";

export const metadata = {
  title: "RepoPilot",
  description: "AI-powered codebase intelligence",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
