/* T27 isolated local browser-native M26 SSE client. Never signs an evaluation. */
"use strict";
(async () => {
  const config = window.__T27_CONFIG__;
  const node = document.getElementById("receipt");
  const start = performance.now();
  const receipt = {
    schema: "m27.w5.t27.browser_client_receive.v1",
    transport: "chrome_fetch_readable_stream",
    context: "local_loopback_nonprod_fixture",
    http_status: null,
    event_sequence: [],
    observed_chunk_count: 0,
    first_substantive_utf8_ms: null,
    first_substantive_event_index: null,
    first_substantive_sha256: null,
    first_substantive_byte_length: null,
    terminal_ms: null,
    terminal_event_index: null,
    cited_before_terminal: false,
    source_native_rights_verified: false,
    external_client_ack_signed: false,
    verified_real_app: false,
    outcome: "ERROR",
    error_code: null
  };
  const emit = () => {
    node.textContent = JSON.stringify(receipt);
    node.dataset.done = "yes";
  };
  const hexdigest = async text => {
    const raw = new TextEncoder().encode(text);
    const bytes = await crypto.subtle.digest("SHA-256", raw);
    return Array.from(new Uint8Array(bytes)).map(b => b.toString(16).padStart(2, "0")).join("");
  };
  const consume = async response => {
    if (!response.body || !response.body.getReader) throw new Error("NO_NATIVE_READER");
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8", { fatal: true });
    let buffer = "";
    let done = false;
    let eventNumber = 0;
    while (!done) {
      const next = await reader.read();
      if (next.done) break;
      receipt.observed_chunk_count += 1;
      buffer += decoder.decode(next.value, { stream: true }).replace(/\r\n/g, "\n");
      if (buffer.length > 1048576) throw new Error("SSE_BUFFER_LIMIT");
      while (buffer.includes("\n\n")) {
        const offset = buffer.indexOf("\n\n");
        const raw = buffer.slice(0, offset);
        buffer = buffer.slice(offset + 2);
        const eventLine = raw.split("\n").find(line => line.startsWith("event: "));
        const dataLine = raw.split("\n").find(line => line.startsWith("data: "));
        if (!eventLine || !dataLine) throw new Error("INVALID_SSE_FRAME");
        const event = eventLine.slice(7);
        const payload = JSON.parse(dataLine.slice(6));
        if (payload.schema_version !== "knowledge-engine-m26-verified-stream/v1" ||
            payload.event !== event) throw new Error("SSE_SCHEMA_MISMATCH");
        receipt.event_sequence.push(event);
        eventNumber += 1;
        if ((event === "verified_claim_ready" || event === "cited_segment_ready") &&
            typeof payload.text === "string" && payload.text.trim() &&
            Array.isArray(payload.citations) && payload.citations.length > 0 &&
            receipt.first_substantive_utf8_ms === null) {
          receipt.first_substantive_utf8_ms = performance.now() - start;
          receipt.first_substantive_event_index = eventNumber;
          receipt.first_substantive_byte_length = new TextEncoder().encode(payload.text).length;
          receipt.first_substantive_sha256 = await hexdigest(payload.text);
        }
        if (["final_answer_done", "safe_abstention_done", "error"].includes(event)) {
          receipt.terminal_ms = performance.now() - start;
          receipt.terminal_event_index = eventNumber;
          receipt.outcome = event === "final_answer_done" ? "COMPLETE" :
            event === "safe_abstention_done" ? "REJECTED" : "ERROR";
          done = true;
          break;
        }
      }
    }
    receipt.cited_before_terminal =
      receipt.first_substantive_event_index !== null &&
      receipt.terminal_event_index !== null &&
      receipt.first_substantive_event_index < receipt.terminal_event_index &&
      receipt.first_substantive_utf8_ms < receipt.terminal_ms;
    if (receipt.terminal_event_index === null) {
      receipt.outcome = "ERROR";
      receipt.error_code = "NO_TERMINAL_EVENT";
    }
    try { await reader.cancel(); } catch (_) { /* stream already closed */ }
  };
  try {
    if (!config || typeof config.token !== "string") throw new Error("MISSING_LOCAL_CONFIG");
    const response = await fetch("/api/m26/query/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": config.token ? "Bearer " + config.token : "",
        "x-m26-owner-subject-hash": config.owner
      },
      body: JSON.stringify({ question: config.mode === "safe" ? "T27 local safe abstention fixture" : "T27 local browser transport receipt" }),
      credentials: "omit",
      cache: "no-store"
    });
    receipt.http_status = response.status;
    if (response.status !== 200) {
      receipt.outcome = "REJECTED";
      receipt.error_code = "HTTP_" + response.status;
    } else {
      await consume(response);
    }
  } catch (err) {
    receipt.outcome = "ERROR";
    receipt.error_code = String(err && err.message || "CLIENT_FAILURE").slice(0, 80);
  }
  receipt.elapsed_ms = performance.now() - start;
  receipt.browser_user_agent = navigator.userAgent;
  emit();
})();