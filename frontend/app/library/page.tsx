import { Search, Sparkles } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { VideoList } from "@/components/video-list";
import { Badge, Input, Panel } from "@/components/ui";
import { listVideos } from "@/lib/api";

type LibraryPageProps = {
  searchParams: Promise<{ search?: string; category?: string }>;
};

export default async function LibraryPage({ searchParams }: LibraryPageProps) {
  const params = await searchParams;
  const data = await listVideos({ search: params.search, category: params.category, limit: 50 }).catch(() => ({
    items: [],
    total: 0,
    limit: 50,
    offset: 0
  }));
  const categories = Array.from(new Set(data.items.map((video) => video.summary?.category).filter(Boolean))) as string[];

  return (
    <AppShell>
      <div className="space-y-7">
        <div className="grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <Badge className="border-accent/30 bg-white text-foreground">
              <Sparkles size={13} />
              Memory Archive
            </Badge>
            <h1 className="mt-4 text-5xl font-black leading-[0.95] tracking-normal sm:text-6xl">Video Library</h1>
            <p className="mt-4 max-w-xl text-sm leading-7 text-muted-foreground">
              这里不是列表，而是你过去收藏、理解和等待重新被调用的视频记忆。
            </p>
          </div>
          <div className="rounded-[24px] border border-border bg-white px-6 py-5 shadow-panel">
            <p className="text-sm text-muted-foreground">Total memories</p>
            <p className="mt-1 text-4xl font-black">{data.total}</p>
          </div>
        </div>

        <Panel className="p-5">
          <form className="grid gap-3 md:grid-cols-[1fr_220px_112px]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-4 top-3.5 text-muted-foreground" size={17} />
              <Input name="search" defaultValue={params.search ?? ""} className="pl-11" placeholder="搜索我的视频记忆，例如 AI Agent 创业" />
            </div>
            <Input name="category" defaultValue={params.category ?? ""} placeholder="分类" />
            <button className="h-12 rounded-full bg-foreground px-5 text-sm font-semibold text-primary-foreground transition hover:-translate-y-0.5 hover:shadow-panel" type="submit">
              搜索
            </button>
          </form>
          {categories.length ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {categories.map((category) => (
                <a key={category} href={`/library?category=${encodeURIComponent(category)}`}>
                  <Badge className="bg-white hover:border-primary hover:text-primary">{category}</Badge>
                </a>
              ))}
            </div>
          ) : null}
        </Panel>

        <VideoList videos={data.items} />
      </div>
    </AppShell>
  );
}
