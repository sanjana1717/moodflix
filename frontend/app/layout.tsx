import './globals.css';
import type { Metadata, Viewport } from 'next';

export const metadata: Metadata = {
  title: 'MOODFLIX — Movies, anime, series and books for your mood',
  description: 'Tell MOODFLIX how you feel and get real, poster-first recommendations for movies, anime, TV series and books, with spoiler-free reasons.',
};

export const viewport: Viewport = { themeColor: '#FFF9F0', width: 'device-width', initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
