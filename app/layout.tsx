import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Loki Trading Dashboard',
  description: 'Modern Vercel-ready dashboard for the Loki trading platform.'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
