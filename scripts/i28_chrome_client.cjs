"use strict";
/* I28 bound local browser reader, exactly the unchanged T27 client.js is served by Python. */
const fs = require("fs");
const puppeteer = require("puppeteer");
(async () => {
  const [port, receiptPath] = process.argv.slice(2);
  const browser = await puppeteer.launch({
    headless: "new",
    executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    args: ["--no-first-run", "--disable-extensions", "--disable-background-networking", "--no-default-browser-check"]
  });
  try {
    const page = await browser.newPage();
    await page.goto("http://127.0.0.1:" + port + "/", {waitUntil: "load", timeout: 30000});
    await page.waitForFunction("document.getElementById('receipt')?.dataset.done === 'yes'", {timeout: 30000});
    const result = await page.$eval("#receipt", node => JSON.parse(node.textContent));
    result.chrome_client_pid_observation = "browser_process_untrusted_for_external_attestation";
    fs.writeFileSync(receiptPath, JSON.stringify(result, null, 2) + "\n");
    if (result.outcome !== "COMPLETE" || !result.cited_before_terminal ||
        !(result.first_substantive_byte_length > 0)) process.exitCode = 21;
    console.log(JSON.stringify({outcome:result.outcome, cited:result.cited_before_terminal,
      first_ms:result.first_substantive_utf8_ms, terminal_ms:result.terminal_ms,
      event_count:result.event_sequence.length}));
  } finally { await browser.close(); }
})().catch(error => { console.error(String(error)); process.exitCode = 20; });
