import { Search } from "lucide-react";
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
      <div className="space-y-6">
        <div>
          <Badge className="bg-white">知识库</Badge>
          <h1 className="mt-3 text-3xl font-semibold tracking-normal">视频知识库</h1>
          <p className="mt-2 text-sm text-muted-foreground">按标题、描述、链接和分类筛选你已经收藏的视频。</p>
        </div>

        <Panel className="p-4">
          <form className="grid gap-3 md:grid-cols-[1fr_220px_96px]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-2.5 text-muted-foreground" size={17} />
              <Input name="search" defaultValue={params.search ?? ""} className="pl-9" placeholder="搜索关键词，例如 AI Agent 创业" />
            </div>
            <Input name="category" defaultValue={params.category ?? ""} placeholder="分类" />
            <button className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground" type="submit">
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
