/* SPDX-License-Identifier: AGPL-3.0-only
 * Host supplies a short-lived bearer in memory, scoped to one explicit backend origin.
 * Never take credentials from query strings or browser persistence.
 */
(function () {
  "use strict";
  window.BelayAuth = {
    async headers(base) {
      const url = new URL(base, window.location.href);
      const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
      if (url.username || url.password || url.search || url.hash ||
          (url.protocol !== "https:" && !(url.protocol === "http:" && local)) ||
          window.BELAY_AUTH_ORIGIN !== url.origin ||
          typeof window.BELAY_GET_ACCESS_TOKEN !== "function") {
        throw new Error("Host authentication is not configured for this backend");
      }
      const token = await window.BELAY_GET_ACCESS_TOKEN();
      if (typeof token !== "string" || !token || /[\r\n]/.test(token)) {
        throw new Error("Host authentication did not provide an access token");
      }
      const headers = { "Content-Type": "application/json", Authorization: "Bearer " + token };
      if (window.BELAY_INSTITUTION_ID && window.BELAY_CLASS_ID) {
        headers["X-Belay-Institution"] = window.BELAY_INSTITUTION_ID;
        headers["X-Belay-Class"] = window.BELAY_CLASS_ID;
      }
      return headers;
    }
  };
})();
