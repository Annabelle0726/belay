/* SPDX-License-Identifier: AGPL-3.0-only */
// Plain text only. Never display arbitrary provider errors or another scope's usage.
globalThis.belayControlMessage = function (detail, retryAfter) {
  const code = detail && typeof detail === "object" ? detail.code : "";
  const messages = {
    poll_limited: "Status was checked too recently. Waiting before checking the same request again; your draft has not been sent.",
    provider_auth_failed: "Sol could not generate feedback because the model service rejected its credentials. Please contact course support. Your draft has been kept.",
    request_not_admitted: "The previous request was not accepted and is now closed. No question was resent. You can choose Ask Sol to submit your current question or discuss the latest run.",
    publication_unavailable: "Saved publication could not be verified. Check status later; do not resubmit this request.",
    conversation_conflict: "This conversation changed or its turn lease ended. Refresh history before a new request.",
    conversation_unavailable: "This conversation is unavailable, expired, deleted or no longer authorized. Its old request will not be resubmitted.",
    saved_database_mismatch: "Saved Ask is not configured on this server. Please contact course support.",
    operation_conflict: "This request ID belongs to different input. Check the original request status.",
    authorization_revoked: "Access to this request was withdrawn. Its result is unavailable.",
    authorization_unavailable: "Request authorization is temporarily unavailable. Check status later.",
    budget_exhausted: "The usage limit has been reached. Please contact your course support team.",
    inference_window_expired: "The authorized tutor usage window has expired. Please contact course support.",
    execution_deadline: "The server execution deadline was reached. The result is not confirmed; check this request's status before submitting again.",
    worker_lost: "The worker stopped responding. The result is not confirmed; check this request's status before submitting again.",
    rate_limited: "Requests are arriving too quickly. Please try again shortly.",
    queue_full: "The tutor is busy. Please try again shortly.",
    concurrency_limited: "The tutor is busy. Please try again shortly.",
    reply_unavailable: "The quoted reply is no longer available. Remove the reference to ask a new question, or choose an available reply.",
    reply_protocol_unavailable: "This server needs an update before it can accept quoted questions. Your draft is unchanged and no new question was submitted. Remove the reference to ask without it, or contact course support.",
    request_invalid: "The server did not accept this request. Your draft is unchanged. Check the reference or contact course support before trying again.",
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
    result_expired: "This response can no longer be restored.",
    recovery_unavailable: "Request recovery storage is unavailable. Enable browser storage and check status before submitting again.",
    content_not_storable: "This request cannot be temporarily stored for recovery. Please remove personal information or contact course support.",
    jobs_disabled: "Ask is not enabled on this server. Please contact your course support team.",
    jobs_not_configured: "Ask recovery is not configured. Please contact your course support team.",
  };
  let message = messages[code] || "The request could not be completed. Please contact your course support team.";
  const seconds = Number(retryAfter);
  if (!["execution_unknown", "request_timeout", "request_lost", "invalid_response"].includes(code) &&
      retryAfter && Number.isInteger(seconds) && seconds > 0 && seconds <= 3600) {
    message += ` You can retry in ${seconds} seconds.`;
  }
  return message;
};
