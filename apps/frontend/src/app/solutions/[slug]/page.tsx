import { notFound } from "next/navigation";

import SolutionPage from "@/components/marketing/SolutionPage";
import { marketingPages } from "@/components/marketing/landing-pages";

type PageProps = {
  params: Promise<{ slug: string }>;
};

export function generateStaticParams() {
  return marketingPages.map((page) => ({ slug: page.slug }));
}

export async function generateMetadata({ params }: PageProps) {
  const { slug } = await params;
  const page = marketingPages.find((item) => item.slug === slug);

  return {
    title: page ? `${page.eyebrow} | CloudCare` : "CloudCare Solutions",
    description: page?.summary ?? "CloudCare solutions for multi-cloud FinOps execution.",
  };
}

export default async function Page({ params }: PageProps) {
  const { slug } = await params;
  const page = marketingPages.find((item) => item.slug === slug);

  if (!page) {
    notFound();
  }

  return <SolutionPage page={page} />;
}
