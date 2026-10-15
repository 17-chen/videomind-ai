"use client";

import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useLanguage, useTranslator } from "@/lib/language";
import { LIBRARY_PAGE_SIZE, libraryHref, type LibraryFilters } from "@/lib/library";

export function LibraryPagination({ page, total, count, filters }: {
  page: number;
  total: number;
  count: number;
  filters: LibraryFilters;
}) {
  const { language } = useLanguage();
  const tx = useTranslator();
  if (!total) return null;
  const pages = Math.ceil(total / LIBRARY_PAGE_SIZE);
  const start = (page - 1) * LIBRARY_PAGE_SIZE + 1;
  const end = start + count - 1;
  const linkStyle = "inline-flex h-11 items-center justify-center gap-1 rounded-full border border-border bg-white px-4 text-sm font-semibold transition hover:border-foreground";

  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <p className="text-sm text-muted-foreground" role="status">
        {language === "zh" ? `显示第 ${start}–${end} 条，共 ${total} 条` : `Showing ${start}–${end} of ${total}`}
      </p>
      {pages > 1 ? (
        <nav aria-label={tx("视频库分页")} className="flex items-center gap-3">
          {page > 1 ? (
            <Link href={libraryHref(filters, page - 1)} className={linkStyle} rel="prev">
              <ChevronLeft size={16} aria-hidden="true" />{tx("上一页")}
            </Link>
          ) : <span aria-disabled="true" className={`${linkStyle} opacity-40`}>{tx("上一页")}</span>}
          <span className="text-sm font-semibold">
            {language === "zh" ? `第 ${page} / ${pages} 页` : `Page ${page} / ${pages}`}
          </span>
          {page < pages ? (
            <Link href={libraryHref(filters, page + 1)} className={linkStyle} rel="next">
              {tx("下一页")}<ChevronRight size={16} aria-hidden="true" />
            </Link>
          ) : <span aria-disabled="true" className={`${linkStyle} opacity-40`}>{tx("下一页")}</span>}
        </nav>
      ) : null}
    </div>
  );
}
