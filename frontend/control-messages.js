/* SPDX-License-Identifier: AGPL-3.0-only */
// Plain text only. Never display arbitrary provider errors or another scope's usage.
globalThis.belayControlMessage = function (detail, retryAfter) {
  const code = detail && typeof detail === "object" ? detail.code : "";
  const messages = {
    budget_exhausted: "The usage limit has been reached. Please contact your course support team.",
    rate_limited: "Requests are arriving too quickly. Please try again shortly.",
    queue_full: "The tutor is busy. Please try again shortly.",
    concurrency_limited: "The tutor is busy. Please try again shortly.",
    coordinator_unavailable: "The tutor is temporarily unavailable. Please try again later.",
    verified_execution_required: "The tutor is not ready for requests. Please contact your course support team.",
    unresolved_overrun: "The tutor is temporarily unavailable. Please contact your course support team.",
    queue_expired: "Your request waited too long. Please submit it again.",
    cancel_requested: "Cancellation was requested. Work already in progress may take time to stop.",
    payload_too_large: "This request is too large. Please shorten it and try again.",
    execution_unknown: "The request's result is not confirmed. It may still be running. Please contact your course support team before submitting again.",
    request_timeout: "Waiting timed out. The request may still be running. Please contact your course support team before submitting again.",
    request_lost: "The connection was lost. The request may still be running. Please contact your course support team before submitting again.",
    invalid_response: "A valid answer was not received. The request may have run. Please contact your course support team before submitting again.",
  };
  let message = messages[code] || "The request could not be completed. Please contact your course support team.";
  const seconds = Number(retryAfter);
  if (!["execution_unknown", "request_timeout", "request_lost", "invalid_response"].includes(code) &&
      retryAfter && Number.isInteger(seconds) && seconds > 0 && seconds <= 3600) {
    message += ` You can retry in ${seconds} seconds.`;
  }
  return message;
};
