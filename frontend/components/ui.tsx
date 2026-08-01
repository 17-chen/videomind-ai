import { cn } from "@/lib/utils";
import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, TextareaHTMLAttributes } from "react";

export function Button({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(
        "inline-flex h-12 items-center justify-center gap-2 rounded-full border border-transparent bg-primary px-6 text-sm font-semibold text-primary-foreground transition duration-300 hover:-translate-y-0.5 hover:shadow-float disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-none",
        className
      )}
      {...props}
    />
  );
}

export function SecondaryButton({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(
        "inline-flex h-12 items-center justify-center gap-2 rounded-full border border-border bg-white px-6 text-sm font-semibold text-foreground transition duration-300 hover:-translate-y-0.5 hover:border-foreground hover:shadow-panel disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-none",
        className
      )}
      {...props}
    />
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-12 w-full rounded-full border border-border bg-white px-5 text-sm outline-none transition placeholder:text-muted-foreground focus:border-foreground focus:ring-4 focus:ring-accent/10",
        className
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "min-h-32 w-full resize-y rounded-[24px] border border-border bg-white px-5 py-4 text-sm outline-none transition placeholder:text-muted-foreground focus:border-foreground focus:ring-4 focus:ring-accent/10",
        className
      )}
      {...props}
    />
  );
}

export function Panel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "memory-surface rounded-[24px] border border-border/80 shadow-panel transition duration-300 hover:-translate-y-1 hover:shadow-float",
        className
      )}
      {...props}
    />
  );
}

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex h-7 items-center gap-1 rounded-full border border-border bg-muted px-3 text-xs font-semibold text-muted-foreground",
        className
      )}
      {...props}
    />
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center rounded-[24px] border border-dashed border-border bg-white/70 px-6 text-center">
      <p className="text-base font-semibold">{title}</p>
      <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{description}</p>
    </div>
  );
}
