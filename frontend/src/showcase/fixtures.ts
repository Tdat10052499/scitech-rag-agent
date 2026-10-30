// ILLUSTRATIVE DATA for the design-system showcase only. Not produced by the system.
// - Paper titles, arXiv ids, dates and categories are real metadata of well-known papers.
// - Snippets are short paraphrases written for the showcase, not quotations from the papers.
// - Answer texts are written by hand to exercise the components; they are not agent output.
// - Items marked "synthetic" are invented on purpose to test edge cases (long title, missing fields).
import type { AssistantMessage, Source, UserMessage } from "../types";

export const ILLUSTRATIVE_NOTE =
  "Illustrative data: real paper metadata, hand-written answers and paraphrased snippets. Nothing here comes from the agent.";

export const SOURCES = {
  rag: {
    chunk_id: "2005.11401#0",
    doc_id: "2005.11401",
    title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
    score: 0.81,
    url: "https://arxiv.org/abs/2005.11401",
    snippet: "Paraphrase: combines a pre-trained sequence-to-sequence generator with a dense index of Wikipedia passages that a neural retriever searches for each input.",
    source: "arxiv",
    published_at: "2020-05-22",
    categories: ["cs.CL", "cs.LG"],
  },
  dpr: {
    chunk_id: "2004.04906#0",
    doc_id: "2004.04906",
    title: "Dense Passage Retrieval for Open-Domain Question Answering",
    score: 0.77,
    url: "https://arxiv.org/abs/2004.04906",
    snippet: "Paraphrase: questions and passages are embedded by two encoders into one vector space, and retrieval is a nearest-neighbour search over the passage vectors.",
    source: "arxiv",
    published_at: "2020-04-10",
    categories: ["cs.CL"],
  },
  wiki: {
    chunk_id: "wiki-Retrieval-augmented_generation#2",
    doc_id: "wiki-Retrieval-augmented_generation",
    title: "Retrieval-augmented generation",
    score: 0.7,
    url: "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
    snippet: "Paraphrase: an encyclopedia overview of the technique, its typical pipeline (index, retrieve, generate) and common uses.",
    source: "wikipedia",
    published_at: "2025-09-14",
  },
  lost: {
    chunk_id: "2307.03172#0",
    doc_id: "2307.03172",
    title: "Lost in the Middle: How Language Models Use Long Contexts",
    score: 0.79,
    url: "https://arxiv.org/abs/2307.03172",
    snippet:
      "Paraphrase: in multi-document question answering and key-value retrieval, performance was highest when the relevant information was at the start or end of the input context and dropped when it sat in the middle, even for models built for long contexts. The study varies the number of documents and the position of the relevant one to separate both effects.",
    source: "arxiv",
    published_at: "2023-07-06",
    categories: ["cs.CL"],
  },
  selfRag: {
    chunk_id: "2310.11511#0",
    doc_id: "2310.11511",
    title: "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection",
    score: 0.72,
    url: "https://arxiv.org/abs/2310.11511",
    snippet: "Paraphrase: the model decides when to retrieve and emits reflection tokens to judge the relevance and support of the passages it uses.",
    source: "arxiv",
    published_at: "2023-10-17",
    categories: ["cs.CL", "cs.AI", "cs.LG"],
  },
  attention: {
    chunk_id: "1706.03762#0",
    doc_id: "1706.03762",
    title: "Attention Is All You Need",
    score: 0.82,
    url: "https://arxiv.org/abs/1706.03762",
    snippet: "Paraphrase: a sequence transduction architecture based only on attention, without recurrence or convolution.",
    source: "arxiv",
    published_at: "2017-06-12",
    categories: ["cs.CL", "cs.LG"],
  },
  // --- synthetic edge cases ---
  longTitle: {
    chunk_id: "synthetic-001#3",
    doc_id: "synthetic-001",
    title:
      "Synthetic example: a deliberately long paper title that wraps over three or more lines in the narrow sources panel, with Vietnamese text — Mô hình ngôn ngữ lớn và truy xuất tăng cường cho câu hỏi khoa học",
    score: 0.6,
    url: "https://example.org/synthetic-001",
    snippet:
      "Synthetic: a long excerpt to test clamping and the 'Show full excerpt' toggle. It keeps going for a while so that it needs more than three lines at the width of the panel, and it includes a long unbroken token such as retrieval-augmented-generation-with-very-long-hyphenated-compound-terms to check that it wraps instead of widening the page.",
    source: "openalex",
    published_at: "2024",
    categories: ["cs.CL", "cs.IR", "cs.AI", "cs.LG", "stat.ML"],
  },
  bare: {
    chunk_id: "synthetic-002#0",
    doc_id: "synthetic-002",
    title: "Synthetic example: source with only the required fields (no link, date, kind or categories)",
    score: 0.5,
  },
  untitled: {
    chunk_id: "synthetic-003#0",
    doc_id: "synthetic-003",
    title: "",
    score: 0.4,
    snippet: "Synthetic: the title field is empty; the UI shows a neutral placeholder instead of inventing one.",
  },
  unsafeLink: {
    chunk_id: "synthetic-004#0",
    doc_id: "synthetic-004",
    title: "Synthetic example: a non-http URL is not turned into a link",
    score: 0.45,
    url: "javascript:alert('not linked')",
    source: "arxiv",
    published_at: "2021-02-30",
  },
} satisfies Record<string, Source>;

export const user = (id: string, text: string): UserMessage => ({ id, role: "user", text });

const assistant = (over: Partial<AssistantMessage> & { id: string }): AssistantMessage => ({
  role: "assistant",
  text: "",
  sources: [],
  followups: [],
  insufficientEvidence: false,
  status: "done",
  ...over,
});

// --- A two-turn conversation where both answers cite [1] and mean different papers. ---
export const Q1 = "What is retrieval-augmented generation?";
export const Q2 = "Does giving the model more retrieved passages always help?";

export const TURN_1 = assistant({
  id: "a1",
  text:
    "Retrieval-augmented generation (RAG) pairs a language model with a retriever: for each question it fetches passages from an external index and conditions the answer on them [1]. " +
    "The retriever is often a **dense passage retriever**, which embeds questions and passages in the same vector space [2].\n\n" +
    "Because the evidence is fetched when the question is asked, the index can be updated without retraining the model [1][3].",
  sources: [SOURCES.rag, SOURCES.dpr, SOURCES.wiki],
  followups: ["How does a dense retriever differ from BM25?", "Can the retriever and the generator be trained together?", "What are common failure modes of RAG?"],
});

export const TURN_2 = assistant({
  id: "a2",
  text:
    "Not necessarily. In multi-document question answering, accuracy was highest when the relevant passage was at the start or end of the context and dropped when it was in the middle [1].\n\n" +
    "Some methods let the model decide when to retrieve and judge the passages it uses, instead of always adding more [2].",
  sources: [SOURCES.lost, SOURCES.selfRag, SOURCES.longTitle],
  followups: [
    "How was the position of the relevant passage varied?",
    "Does reranking passages reduce the effect?",
    "Which models were tested in that study?",
    "How does Self-RAG decide when to retrieve?",
  ],
});

export const CONVERSATION = [user("u1", Q1), TURN_1, user("u2", Q2), TURN_2];

// --- Single states for the component gallery ---
export const MISSING_CITATION = assistant({
  id: "m1",
  text: "This answer has two sources. It cites [1] correctly, and also cites [4], which is not in its list: the marker is shown as missing instead of pointing at another paper.",
  sources: [SOURCES.rag, SOURCES.dpr],
});

export const MARKDOWN_SAMPLE = assistant({
  id: "md1",
  text:
    "Two ways to reduce position effects are:\n1. Put the most relevant passage first [1].\n2. Retrieve fewer, better passages [2].\n\n" +
    "- *Italic* and **bold** text\n- Inline code such as `top_k=5`\n\n" +
    "```\nretriever = DenseRetriever(index='cs.CL', k=5)  # a long line of code scrolls inside its own box instead of widening the page\n```\n\n" +
    "HTML in an answer stays text: <b>not bold</b>.",
  sources: [SOURCES.lost, SOURCES.selfRag],
});

export const SEARCHING = assistant({ id: "s1", status: "searching" });

export const STREAMING = assistant({
  id: "st1",
  status: "answering",
  text: "The Transformer relies only on attention, without recurrence [1]. It is now the",
  sources: [SOURCES.attention],
});

export const INSUFFICIENT_TEXT = "I could not find enough evidence in the corpus to answer this question."; // as backend/src/app/fake_agent.py

export const INSUFFICIENT = assistant({ id: "i1", insufficientEvidence: true, text: INSUFFICIENT_TEXT });

export const ERROR_BEFORE_TEXT = assistant({
  id: "e1",
  status: "error",
  sources: [SOURCES.attention],
  error: { code: "retrieval_failed", message: "Simulated failure (retrieval_failed) from the fake agent." },
});

export const ERROR_AFTER_TEXT = assistant({
  id: "e2",
  status: "error",
  text: "The Transformer relies only on attention, without recurrence [1]. It",
  sources: [SOURCES.attention],
  error: { code: "timeout", message: "Simulated failure (timeout) from the fake agent." },
});

export const TRANSPORT_ERROR = assistant({
  id: "e3",
  status: "error",
  error: { message: "The server is not reachable. Check that the backend is running." }, // as src/api.ts
});

export const LONG_QUESTION =
  "I am comparing retrieval setups for a course project.\nWhich is better for scientific abstracts: dense retrieval, BM25, or a hybrid of both — and does the answer change for Vietnamese queries (câu hỏi tiếng Việt)?\nhttps://example.org/a-very-long-unbroken-link-that-must-wrap-instead-of-overflowing-the-reading-column";
