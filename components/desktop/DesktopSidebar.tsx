'use client';

import React from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';

const imgBrandLogo = '/images/desktop-brand-logo.png';
const imgHouse = '/images/desktop-house.svg';
const imgFish = '/images/desktop-fish.svg';
const imgRecycle = '/images/desktop-recycle.svg';
const imgLightbulb = '/images/desktop-lightbulb.svg';
const imgServer = '/images/desktop-server.svg';
const imgBanknote = '/images/desktop-banknote.svg';
const imgFileText = '/images/desktop-file-text.svg';
const imgCircleHelp = '/images/desktop-circle-help.svg';
const imgSettings = '/images/desktop-settings.svg';
const imgFishPond = '/images/desktop-fish-pond.png';

interface NavItem {
  label: string;
  href: string;
  icon: string;
}

const MAIN_NAV_ITEMS: NavItem[] = [
  { label: 'Pusat AI ? Water & BSF', href: '/desktop/ai', icon: imgLightbulb },
  { label: 'Beranda', href: '/desktop/dashboard', icon: imgHouse },
  { label: 'Kolam & Ikan', href: '/desktop/farms', icon: imgFish },
  { label: 'BSF & Sirkular', href: '/desktop/bsf', icon: imgRecycle },
  { label: 'Insight & Rekomendasi', href: '/desktop/insights', icon: imgLightbulb },
  { label: 'Perangkat', href: '/desktop/devices', icon: imgServer },
  { label: 'Pasar & Penjualan', href: '/desktop/harvest', icon: imgBanknote },
  { label: 'Laporan', href: '/desktop/reports', icon: imgFileText },
];

const SUPPORT_NAV_ITEMS: NavItem[] = [
  { label: 'Bantuan', href: '/desktop/help', icon: imgCircleHelp },
  { label: 'Pengaturan', href: '/desktop/settings', icon: imgSettings },
];

export default function DesktopSidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="bg-white border-[#e7eff4] border-r border-solid content-stretch flex flex-col justify-between h-screen sticky top-0 items-start overflow-y-auto pb-[20px] pt-[26px] px-[16px] shrink-0 w-[216px] select-none"
      data-node-id="35:5388"
      data-name="Sidebar"
    >
      <div className="w-full flex flex-col gap-[13px]">
        {/* Brand */}
        <div
          className="content-stretch flex items-start overflow-clip relative shrink-0 w-[185px] mb-2"
          data-node-id="81:291"
          data-name="Brand"
        >
          <Link href="/desktop/dashboard" className="flex items-center gap-[5px]">
            <div className="h-[44px] relative shrink-0 w-[107px]">
              <Image
                alt="Fiscycle logo"
                className="object-contain"
                src={imgBrandLogo}
                width={107}
                height={44}
                priority
              />
            </div>
          </Link>
        </div>

        {/* Main Navigation */}
        <nav
          className="content-stretch flex flex-col gap-[4px] items-start overflow-clip relative shrink-0 w-full"
          data-node-id="81:295"
          data-name="Main navigation"
        >
          {MAIN_NAV_ITEMS.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== '/desktop/dashboard' && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`content-stretch flex gap-[10px] h-[31px] items-center overflow-clip px-[10px] relative rounded-[6px] shrink-0 w-full transition ${
                  isActive
                    ? 'bg-[#e2f3fc] text-[#1c74a7]'
                    : 'bg-white hover:bg-slate-50 text-[#8192a5]'
                }`}
                data-name="Navigation item"
              >
                <div className="relative shrink-0 size-[17px]">
                  <Image
                    alt=""
                    className="block inset-0 max-w-none size-full"
                    src={item.icon}
                    width={17}
                    height={17}
                  />
                </div>
                <p
                  className={`leading-[1.35] not-italic relative shrink-0 text-[11px] whitespace-nowrap ${
                    isActive ? 'font-bold text-[#1c74a7]' : 'font-normal text-[#8192a5]'
                  }`}
                >
                  {item.label}
                </p>
              </Link>
            );
          })}

          {/* Support Navigation */}
          <div
            className="content-stretch flex flex-col gap-[4px] items-start overflow-clip pt-[15px] relative shrink-0 w-full border-t border-[#e7eff4] mt-2"
            data-node-id="81:340"
            data-name="Support navigation"
          >
            {SUPPORT_NAV_ITEMS.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`content-stretch flex gap-[10px] h-[31px] items-center overflow-clip px-[10px] relative rounded-[6px] shrink-0 w-full transition ${
                    isActive
                      ? 'bg-[#e2f3fc] text-[#1c74a7]'
                      : 'bg-white hover:bg-slate-50 text-[#8192a5]'
                  }`}
                  data-name="Navigation item"
                >
                  <div className="relative shrink-0 size-[17px]">
                    <Image
                      alt=""
                      className="block inset-0 max-w-none size-full"
                      src={item.icon}
                      width={17}
                      height={17}
                    />
                  </div>
                  <p
                    className={`leading-[1.35] not-italic relative shrink-0 text-[11px] whitespace-nowrap ${
                      isActive ? 'font-bold text-[#1c74a7]' : 'font-normal text-[#8192a5]'
                    }`}
                  >
                    {item.label}
                  </p>
                </Link>
              );
            })}
          </div>
        </nav>
      </div>

      {/* Farm Account Card */}
      <div
        className="bg-[#e2f3fc] content-stretch flex flex-col gap-[7px] items-start overflow-clip p-[11px] rounded-[10px] w-full shrink-0 mt-4"
        data-node-id="35:5436"
        data-name="Farm account card"
      >
        <p
          className="font-bold leading-[1.35] not-italic relative shrink-0 text-[#173251] text-[13px] whitespace-nowrap"
          data-node-id="35:5437"
        >
          Tambak Makmur
        </p>
        <div
          className="h-[80px] relative rounded-[6px] shrink-0 w-full overflow-hidden"
          data-node-id="35:5438"
          data-name="Fish pond"
        >
          <Image
            alt="Tambak Makmur"
            className="absolute inset-0 object-cover pointer-events-none rounded-[6px] size-full"
            src={imgFishPond}
            fill
            sizes="162px"
          />
        </div>
        <div className="flex flex-col">
          <p
            className="font-normal leading-[1.35] not-italic relative shrink-0 text-[#8192a5] text-[9px] whitespace-nowrap"
            data-node-id="35:5439"
          >
            ID Mitra
          </p>
          <p
            className="font-semibold leading-[1.35] not-italic relative shrink-0 text-[#173251] text-[10px] whitespace-nowrap"
            data-node-id="35:5440"
          >
            FSC-FARM-0028
          </p>
        </div>
        <Link
          href="/desktop/farms"
          className="bg-white border border-[#a9c9db] border-solid content-stretch flex h-[27px] items-center justify-center overflow-clip relative rounded-[6px] shrink-0 w-full hover:bg-sky-50 transition"
          data-node-id="35:5441"
          data-name="Action"
        >
          <p
            className="font-bold leading-[1.35] not-italic relative shrink-0 text-[#00629b] text-[11px] whitespace-nowrap"
            data-node-id="35:5442"
          >
            Lihat Profil Tambak
          </p>
        </Link>
      </div>
    </aside>
  );
}
