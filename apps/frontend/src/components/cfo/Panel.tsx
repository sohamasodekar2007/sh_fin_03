import type { ReactNode } from "react";

interface Props {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  aside?: ReactNode;
  children: ReactNode;
  delay?: number;
  className?: string;
  bodyClassName?: string;
  /** Tighten or loosen the header block without touching the body. */
  headerClassName?: string;
  /** Long-form version of the subtitle, surfaced on hover/focus only. */
  subtitleHint?: string;
  /**
   * When set, the panel body is replaced by a quiet empty state. Written as
   * setup instructions for a remixer, not as an error.
   */
  empty?: ReactNode;
}

export function Panel({
  eyebrow,
  title,
  subtitle,
  aside,
  children,
  delay = 0,
  className = "",
  bodyClassName = "p-5 pt-0 sm:p-6 sm:pt-0",
  headerClassName = "p-5 sm:p-6",
  subtitleHint,
  empty,
}: Props) {
  return (
    <section
      className={`panel hairline-top stage overflow-hidden ${className}`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <header
        className={`flex flex-wrap items-start justify-between gap-4 ${headerClassName}`}
      >
        <div className="min-w-0">
          {eyebrow && <div className="eyebrow">{eyebrow}</div>}
          <h2 className="mt-1 text-[1.15rem] font-semibold leading-tight text-foreground sm:text-[1.3rem]">
            {title}
          </h2>
          {subtitle && (
            <p
              title={subtitleHint}
              className="mt-1 max-w-xl text-[12px] leading-relaxed text-ink-faint"
            >
              {subtitle}
            </p>
          )}
        </div>

        {!empty && aside && <div className="shrink-0">{aside}</div>}
      </header>
      {empty ? (
        <div className="px-5 pb-10 pt-4 sm:px-6">
          <div className="mx-auto max-w-md text-center text-[12.5px] leading-relaxed text-ink-faint">
            {empty}
          </div>
        </div>
      ) : (
        <div className={bodyClassName}>{children}</div>
      )}
    </section>
  );
}
