// Ratings and clicks for POST /feedback (contract 0.3.0, issue #147). Pure rules and one small client.
// Fields: session_id, message_id (from the `done` event of the rated answer), target (answer | followup),
// rating (up | down | click; click only for a follow-up), followup (the suggestion text, for a follow-up).

export type FeedbackTarget = "answer" | "followup";
export type FeedbackRating = "up" | "down" | "click";

/** What the screen reports: one thumb on an answer, or one click on a follow-up suggestion. */
export type FeedbackItem = {
  messageId: string;
  target: FeedbackTarget;
  rating: FeedbackRating;
  followup?: string;
};

export type FeedbackRequest = {
  session_id: string;
  message_id: string;
  target: FeedbackTarget;
  rating: FeedbackRating;
  followup?: string;
};

/** The JSON body, or `null` when the item breaks the contract (the endpoint would answer 422). */
export function buildFeedback(sessionId: string, item: FeedbackItem): FeedbackRequest | null {
  if (!sessionId || !item.messageId) return null;
  if (item.target === "answer") {
    if (item.rating === "click" || item.followup !== undefined) return null;
    return { session_id: sessionId, message_id: item.messageId, target: "answer", rating: item.rating };
  }
  if (!item.followup) return null;
  return { session_id: sessionId, message_id: item.messageId, target: "followup", rating: item.rating, followup: item.followup };
}

/** Key of one rated thing, so the screen keeps the latest choice per answer or suggestion. */
export function feedbackKey(item: Pick<FeedbackItem, "messageId" | "target" | "followup">): string {
  return `${item.messageId}|${item.target}|${item.followup ?? ""}`;
}

/**
 * POST /feedback. Never throws and never shows an error: the rating stays on screen either way. Returns
 * whether the server accepted it (204). Until the endpoint exists (404) or when the backend is down, the
 * rating is simply not stored.
 */
export async function postFeedback(request: FeedbackRequest): Promise<boolean> {
  try {
    const response = await fetch("/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    return response.ok;
  } catch {
    return false;
  }
}
