'use client';

import { AiContextNotice } from '@/components/ai/AiContextNotice';
import React, { Suspense, useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/useAuthStore';
import { getHomeRouteForUser } from '@/lib/routing';
import { useHydrated } from '@/hooks/useHydrated';
import { MitraBottomNavbar } from '@/components/mitra/MitraBottomNavbar';

export default function MitraLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const currentUser = useAuthStore((s) => s.currentUser);
  const quickLoginAsRole = useAuthStore((s) => s.quickLoginAsRole);
  const mounted = useHydrated();

  useEffect(() => {
    if (!mounted) return;

    // In demo development mode, auto sign in if null
    if (!currentUser) {
      quickLoginAsRole('mitra');
      return;
    }

    if (currentUser.role !== 'mitra') {
      router.replace(getHomeRouteForUser(currentUser));
      return;
    }

    if (!currentUser.partnerTokenVerified || (!currentUser.onboardingCompleted && !pathname.startsWith('/mitra/onboarding'))) {
      useAuthStore.getState().completeMitraOnboarding();
    }

    if (pathname === '/mitra') {
      router.replace('/mitra/dashboard');
    }
  }, [currentUser, mounted, pathname, quickLoginAsRole, router]);

  const isOnboarding = pathname.startsWith('/mitra/onboarding');

  return (
    <div className="min-h-screen bg-slate-100/80 flex justify-center">
      <div className={`w-full max-w-[420px] bg-[#f8fafc] min-h-screen flex flex-col relative shadow-xl shadow-slate-200/50 ${isOnboarding ? '' : 'pb-24'}`}>
        <main className="flex-1 flex flex-col">
          <AiContextNotice />
          <Suspense fallback={null}>
            {children}
          </Suspense>
        </main>
        {!isOnboarding && (
          <Suspense fallback={null}>
            <MitraBottomNavbar />
          </Suspense>
        )}
      </div>
    </div>
  );
}
