// How a `Source` (contract 0.2.1) is described in the UI. Only fields that are present are shown;
// nothing is guessed: no year without a valid date, no link without an http(s) URL.
import type { Source } from "../types";

const KIND_LABELS: Record<NonNullable<Source["source"]>, string> = {
  arxiv: "arXiv",
  openalex: "OpenAlex",
  wikipedia: "Wikipedia",
};

const ISO_DATE = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/;
const ARXIV_ID = /^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?\/\d{7})(?:v\d+)?$/;

export type SourceDescription = {
  title: string; // never empty
  untitled: boolean;
  href?: string; // only http(s); anything else (javascript:, data:, relative) is not linked
  kind?: string; // "arXiv", "Wikipedia", "OpenAlex"
  date?: string; // "2017" for papers, "Revised 2024" for Wikipedia (the date is the revision)
  identifier?: string; // "arXiv:1706.03762", only for arXiv ids
  categories: string[];
  snippet?: string;
};

export function safeHref(url: string | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const parsed = new URL(url.trim());
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}

function year(date: string | undefined): string | undefined {
  const m = date ? ISO_DATE.exec(date.trim()) : null;
  if (!m) return undefined;
  const [y, mo, d] = [Number(m[1]), Number(m[2] ?? 1), Number(m[3] ?? 1)];
  const parsed = new Date(Date.UTC(y, mo - 1, d));
  return parsed.getUTCMonth() === mo - 1 && parsed.getUTCDate() === d ? m[1] : undefined; // rejects 2020-13-01, 2021-02-30
}

export function describeSource(s: Source): SourceDescription {
  const title = s.title?.trim() ?? "";
  const y = year(s.published_at);
  const categories = [...new Set((s.categories ?? []).map((c) => c.trim()).filter(Boolean))];
  const snippet = s.snippet?.trim();
  return {
    title: title || "Untitled source",
    untitled: !title,
    href: safeHref(s.url),
    kind: s.source ? KIND_LABELS[s.source] : undefined,
    date: y && (s.source === "wikipedia" ? `Revised ${y}` : y),
    identifier: s.source === "arxiv" && ARXIV_ID.test(s.doc_id) ? `arXiv:${s.doc_id}` : undefined,
    categories,
    snippet: snippet || undefined,
  };
}
