"use client";

import { useEffect, useRef, useState } from "react";

/** Cubic ease-out — the house curve. */
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

/**
 * Counts a number up from zero on mount (after an optional delay).
 * Uses rAF so it stays in step with the rest of the page-load sequence.
 */
export function useCountUp(target: number, duration = 1400, delay = 0): number {
  const [value, setValue] = useState(0);
  const targetRef = useRef(target);
  targetRef.current = target;

  useEffect(() => {
    let raf = 0;
    let start = 0;
    const from = 0;

    const tick = (now: number) => {
      if (!start) start = now;
      const t = Math.min(1, (now - start) / duration);
      setValue(from + (targetRef.current - from) * easeOut(t));
      if (t < 1) raf = requestAnimationFrame(tick);
      else setValue(targetRef.current);
    };

    const timer = setTimeout(() => {
      raf = requestAnimationFrame(tick);
    }, delay);

    return () => {
      clearTimeout(timer);
      cancelAnimationFrame(raf);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [duration, delay]);

  // If the target changes after the initial count-up, glide to it.
  const settledRef = useRef(false);
  useEffect(() => {
    const t = setTimeout(() => {
      settledRef.current = true;
    }, delay + duration);
    return () => clearTimeout(t);
  }, [delay, duration]);

  useEffect(() => {
    if (!settledRef.current) return;
    let raf = 0;
    let start = 0;
    const from = value;
    const to = target;
    const tick = (now: number) => {
      if (!start) start = now;
      const t = Math.min(1, (now - start) / 520);
      setValue(from + (to - from) * easeOut(t));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  return value;
}

/**
 * Returns true once `delay` ms have elapsed since mount — the primitive the
 * single page-load sequence is built from.
 */
export function useStage(delay: number): boolean {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setOn(true), delay);
    return () => clearTimeout(t);
  }, [delay]);
  return on;
}

/**
 * Resolves a list of CSS custom-property names (e.g. "--signal-deep") to
 * their computed color strings, re-read on mount and whenever the
 * dark-mode class on <html> toggles (ThemeToggle.tsx).
 *
 * Why this exists: `<stop stop-color="var(--x)">` inside an inline SVG
 * <linearGradient> does not reliably resolve CSS custom properties in
 * every browser — the plain `fill="var(--x)"` attribute on ordinary SVG
 * shapes does, but color-stop resolution inside gradients has real,
 * browser-specific gaps and silently falls back to black. Resolving the
 * variable to a concrete color string in JS and using that instead of a
 * live var() reference sidesteps the gap entirely, at the cost of not
 * re-rendering instantly on an OS-level prefers-color-scheme change (it
 * still follows the explicit light/dark toggle, which is what the rest of
 * this app's theming already keys off).
 */
export function useThemeColors(varNames: string[]): Record<string, string> {
  const [colors, setColors] = useState<Record<string, string>>({});

  useEffect(() => {
    const resolve = () => {
      const style = getComputedStyle(document.documentElement);
      const next: Record<string, string> = {};
      for (const name of varNames) {
        next[name] = style.getPropertyValue(name).trim();
      }
      setColors(next);
    };

    resolve();

    const observer = new MutationObserver(resolve);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [varNames.join(",")]);

  return colors;
}

/** Observed width/height of an element, for responsive SVG charts. */
export function useMeasure<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [rect, setRect] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setRect({ width: r.width, height: r.height });
    });
    ro.observe(el);
    const r = el.getBoundingClientRect();
    setRect({ width: r.width, height: r.height });
    return () => ro.disconnect();
  }, []);

  return { ref, ...rect };
}
