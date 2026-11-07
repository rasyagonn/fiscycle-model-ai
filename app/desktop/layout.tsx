import { AiContextNotice } from '@/components/ai/AiContextNotice';
import React from 'react';
import type { Metadata } from 'next';
import DesktopSidebar from '@/components/desktop/DesktopSidebar';

export const metadata: Metadata = {
  title: 'Fiscycle — Desktop Workspace Mitra Tambak',
  description: 'Terminal operasional tambak dan ekosistem budidaya sirkular layar lebar.',
};

export default function DesktopLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="bg-[#f3f9fc] flex min-h-screen text-[#173251] font-sans antialiased overflow-x-hidden">
      {/* 216px Desktop Sidebar matching Figma */}
      <DesktopSidebar />

      {/* Main Desktop Viewport (1224px min content) */}
      <main className="flex-1 min-h-screen overflow-y-auto">
        <AiContextNotice />
        {children}
      </main>
    </div>
  );
}
