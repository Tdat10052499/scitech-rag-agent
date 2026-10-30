import type { ChatError, ErrorCode } from "../types";
import { Button } from "./Button";
import { Callout } from "./Callout";

type Props = {
  error: ChatError;
  partial?: boolean; // part of the answer arrived before the error; that text stays visible above
  onRetry?: () => void; // shown only when the page can resend the question
};

// Titles per contract error code (api.openapi.yaml `Error.code`); `undefined` = the request never
// reached the agent (network, HTTP status, cut stream; see src/api.ts ChatTransportError).
const TITLES: Record<ErrorCode | "transport", string> = {
  llm_unavailable: "The answer service is unavailable",
  retrieval_failed: "The search over the corpus failed",
  timeout: "The answer took too long",
  internal: "Something went wrong while answering",
  transport: "Could not reach the server",
};

export function errorTitle(error: ChatError): string {
  return TITLES[error.code ?? "transport"];
}

/** A technical failure, kept visually apart from "not enough evidence" (which is an answer). */
export function ErrorState({ error, partial = false, onRetry }: Props) {
  return (
    <Callout
      tone="error"
      title={partial ? `The answer stopped early. ${errorTitle(error)}` : errorTitle(error)}
      actions={
        onRetry && (
          <Button size="sm" variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        )
      }
    >
      <p>{error.message}</p>
    </Callout>
  );
}
