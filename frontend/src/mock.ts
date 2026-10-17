import type { Message } from "./types";

// Hard-coded conversation for W2-D1-LDN-1 (layout only; no network). Titles and snippets are
// taken from arXiv abstracts; scores and dates are made up for the mock.
export const mockConversation: Message[] = [
  {
    id: "m1",
    role: "user",
    text: "Is it always better to give an AI more retrieved documents when it answers a question?",
  },
  {
    id: "m2",
    role: "assistant",
    text:
      "Not always. For many long-context models, answer quality first improves and then declines " +
      'as more passages are retrieved, because irrelevant "hard negatives" hurt [1].\n' +
      "Retrieval that optimizes only for relevance can also lower the quality of the final answer [2].",
    sources: [
      {
        chunk_id: "2410.05983#0",
        doc_id: "2410.05983",
        title: "Long-Context LLMs Meet RAG: Overcoming Challenges for Long Inputs in RAG",
        score: 0.84,
        url: "https://arxiv.org/abs/2410.05983",
        snippet:
          "The quality of generated output initially improves first, but then subsequently declines as the number of retrieved passages increases ...",
        source: "arxiv",
        published_at: "2024-10-08",
        categories: ["cs.CL"],
      },
      {
        chunk_id: "2504.07104#0",
        doc_id: "2504.07104",
        title: "Relevance Isn't All You Need: Scaling RAG Systems With Inference-Time Compute Via Multi-Criteria Reranking",
        score: 0.71,
        url: "https://arxiv.org/abs/2504.07104",
        snippet:
          "In standard RAG pipelines, maximizing for context relevance alone can degrade downstream response quality ...",
        source: "arxiv",
        published_at: "2025-04-09",
        categories: ["cs.IR", "cs.CL", "cs.LG"],
      },
    ],
    followups: [
      "What are hard negatives in retrieval?",
      "How can a RAG system reduce their effect?",
      "How many passages should I retrieve?",
    ],
    insufficientEvidence: false,
  },
  {
    id: "m3",
    role: "user",
    text: "Does any paper report a quantum-computing tokenizer for large language models?",
  },
  {
    id: "m4",
    role: "assistant",
    text:
      "I could not find enough evidence in the corpus to answer this question. " +
      "Try rephrasing it, or ask about another topic in LLM and NLP research.",
    sources: [],
    followups: ["What is retrieval-augmented generation?", "How are LLM hallucinations detected?"],
    insufficientEvidence: true,
  },
];
