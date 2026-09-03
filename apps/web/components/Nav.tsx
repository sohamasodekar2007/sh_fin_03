"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

export default function Nav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled ? "py-2.5 bg-bg/85 backdrop-blur-md shadow-[0_2px_20px_-8px_rgba(16,34,46,0.12)]" : "py-4.5"
      }`}
    >
      <div className="mx-auto max-w-6xl px-7 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5 font-display font-bold text-xl text-ink">
          <span className="w-8 h-8 rounded-[10px] bg-gradient-to-br from-brandBlue to-brandTeal inline-block" />
          CloudCare
        </Link>
        <nav className="hidden md:block">
          <ul className="flex gap-9 list-none m-0 p-0">
            <li>
              <a href="/#home" className="text-sm font-medium text-inkSoft hover:text-ink transition-colors">
                Home
              </a>
            </li>
            <li>
              <a href="/#about" className="text-sm font-medium text-inkSoft hover:text-ink transition-colors">
                About
              </a>
            </li>
            <li>
              <a href="/#team" className="text-sm font-medium text-inkSoft hover:text-ink transition-colors">
                Team
              </a>
            </li>
            <li>
              <a href="/#contact" className="text-sm font-medium text-inkSoft hover:text-ink transition-colors">
                Contact us
              </a>
            </li>
          </ul>
        </nav>
        <Link
          href="/login"
          className="inline-flex items-center justify-center rounded-full border-[1.5px] border-line bg-surface px-5 py-2 text-sm font-semibold text-ink hover:border-brandBlue hover:shadow-card transition-all"
        >
          Log in
        </Link>
      </div>
    </header>
  );
}
