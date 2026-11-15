import { ApiError } from "../api/client";

/** Friendly, client-safe wording for an API failure -- never raw backend detail. */
const FRIENDLY_MESSAGE_BY_STATUS: Record<number, string> = {
  0: "CircadianIQ can't be reached right now. Check that the API is running.",
  404: "We couldn't find that participant or result.",
  400: "That request couldn't be completed with the current data.",
  409: "That action was already completed.",
  422: "Some of the information provided wasn't valid.",
  503: "CircadianIQ's inference service is temporarily unavailable. Please try again shortly.",
  500: "Something went wrong on our end. Please try again.",
};

export function friendlyErrorMessage(error: unknown): string {
  return error instanceof ApiError
    ? (FRIENDLY_MESSAGE_BY_STATUS[error.status] ?? error.message)
    : "Something went wrong. Please try again.";
}
