import { Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getServerTranslator } from "@/lib/server-language";
import { AppShell } from "@/components/app-shell";
import { ApiErrorPanel } from "@/components/api-error-panel";
import { VideoList } from "@/components/video-list";
import { LibraryPagination } from "@/components/library-pagination";
import { Badge, EmptyState, Input, Panel } from "@/components/ui";
import { listVideoCategories, listVideos } from "@/lib/api";
import { LIBRARY_PAGE_SIZE, libraryHref, libraryPage } from "@/lib/library";
import { getServerAccessToken } from "@/lib/supabase/server";

type LibraryPageProps = {
  searchParams: Promise<{ search?: string | string[]; category?: string | string[]; page?: string | string[] }>;
};

export default async function LibraryPage({ searchParams }: LibraryPageProps) {
  const tx = await getServerTranslator();
  const params = await searchParams;
  const filters = {
    search: typeof params.search === "string" ? params.search.trim() : undefined,
    category: typeof params.category === "string" ? params.category.trim() : undefined,
  };
  const page = libraryPage(params.page);
  const accessToken = await getServerAccessToken();
  const [data, categories] = await Promise.all([
    listVideos({ ...filters, limit: LIBRARY_PAGE_SIZE, offset: (page - 1) * LIBRARY_PAGE_SIZE }, accessToken).catch(() => null),
    listVideoCategories(accessToken).catch(() => []),
  ]);
  if (!data) {
    return <AppShell><ApiErrorPanel /></AppShell>;
  }
  const lastPage = Math.max(1, Math.ceil(data.total / LIBRARY_PAGE_SIZE));
  if (page > lastPage) redirect(libraryHref(filters, lastPage));
  const hasFilters = Boolean(filters.search || filters.category);

  return (
    <AppShell>
      <div className="space-y-7">
        <div className="grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <Badge className="border-accent/30 bg-white text-foreground">
              <Sparkles size={13} />
              {tx("Memory Archive")}
            </Badge>
            <h1 className="mt-4 text-5xl font-black leading-[0.95] tracking-normal sm:text-6xl">{tx("Video Library")}</h1>
            <p className="mt-4 max-w-xl text-sm leading-7 text-muted-foreground">
              {tx("这里不是列表，而是你过去收藏、理解和等待重新被调用的视频记忆。")}
            </p>
          </div>
          <div className="rounded-[24px] border border-border bg-white px-6 py-5 shadow-panel">
            <p className="text-sm text-muted-foreground">{tx(hasFilters ? "匹配的视频" : "Total memories")}</p>
            <p className="mt-1 text-4xl font-black">{data.total}</p>
          </div>
        </div>

        <Panel className="p-5">
          <form key={libraryHref(filters)} action="/library" className="grid gap-3 md:grid-cols-[1fr_220px_112px]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-4 top-3.5 text-muted-foreground" size={17} />
              <Input name="search" aria-label={tx("搜索视频")} maxLength={120} defaultValue={filters.search ?? ""} className="pl-11" placeholder={tx("搜索标题、描述或 AI 摘要")} />
            </div>
            <Input name="category" aria-label={tx("分类")} maxLength={120} defaultValue={filters.category ?? ""} placeholder={tx("分类")} />
            <button className="h-12 rounded-full bg-foreground px-5 text-sm font-semibold text-primary-foreground transition hover:-translate-y-0.5 hover:shadow-panel" type="submit">
              {tx("搜索")}
            </button>
          </form>
          {categories.length ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {categories.map((category) => (
                <Link key={category} href={libraryHref({ search: filters.search, category })} aria-current={filters.category === category ? "page" : undefined}>
                  <Badge className={filters.category === category ? "border-primary bg-primary/10 text-primary" : "bg-white hover:border-primary hover:text-primary"}>{category}</Badge>
                </Link>
              ))}
            </div>
          ) : null}
          {hasFilters ? <Link href="/library" className="mt-4 inline-block text-sm font-semibold underline underline-offset-4">{tx("清除筛选")}</Link> : null}
        </Panel>

        {!data.items.length && hasFilters ? (
          <EmptyState title={tx("没有匹配的视频")} description={tx("试试其他关键词或清除筛选，已有视频仍保留在知识库中。")} />
        ) : <VideoList videos={data.items} />}
        <LibraryPagination page={page} total={data.total} count={data.items.length} filters={filters} />
      </div>
    </AppShell>
  );
}
