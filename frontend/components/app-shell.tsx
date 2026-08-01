"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bot, Circle, LayoutDashboard, Library, PlaySquare, Search } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "首页", icon: LayoutDashboard },
  { href: "/dashboard", label: "工作台", icon: PlaySquare },
  { href: "/library", label: "知识库", icon: Library },
  { href: "/chat", label: "视频问答", icon: Bot }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen pb-20 md:pb-0">
      <header className="sticky top-0 z-20 bg-background/78 backdrop-blur-xl">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-3">
            <span className="relative flex h-11 w-11 items-center justify-center rounded-full border border-border bg-white shadow-panel">
              <Circle size={18} className="fill-foreground text-foreground" />
              <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-accent" />
            </span>
            <span>
              <span className="block text-sm font-bold leading-4">VideoMind</span>
              <span className="block text-xs text-muted-foreground">AI Video Memory</span>
            </span>
          </Link>
          <nav className="hidden items-center gap-1 rounded-full border border-border bg-white/82 p-1 shadow-panel md:flex">
            {navItems.map((item) => {
              const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "inline-flex h-10 items-center gap-2 rounded-full px-4 text-sm font-medium text-muted-foreground transition hover:text-foreground",
                    active && "bg-foreground text-primary-foreground shadow-sm hover:text-primary-foreground"
                  )}
                >
                  <Icon size={16} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <Link
            href="/library"
            className="hidden h-11 items-center gap-2 rounded-full border border-border bg-white px-4 text-sm font-semibold text-foreground shadow-panel transition hover:-translate-y-0.5 hover:shadow-float sm:inline-flex"
          >
            <Search size={16} />
            Search memory
          </Link>
        </div>
      </header>
      <main className="page-enter mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      <nav className="fixed inset-x-3 bottom-3 z-30 rounded-full border border-border bg-white/90 px-2 py-2 shadow-float backdrop-blur-xl md:hidden">
        <div className="grid grid-cols-4 gap-1">
          {navItems.map((item) => {
            const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex h-12 flex-col items-center justify-center gap-1 rounded-md text-[11px] text-muted-foreground",
                  active && "rounded-full bg-foreground text-primary-foreground shadow-sm"
                )}
              >
                <Icon size={17} />
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
