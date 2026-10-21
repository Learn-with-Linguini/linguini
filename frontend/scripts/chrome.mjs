// Drive a headless Google Chrome page over the DevTools protocol. Shared by the post export scripts.
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const chrome = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
export const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

/** Open `url` in a fresh headless Chrome and return helpers to talk to the page. */
export async function openPage(url, { width = 1280, height = 900, scale = 1 } = {}) {
  const port = 9400 + Math.floor(Math.random() * 400);
  const proc = spawn(chrome, [
    "--headless=new", "--disable-gpu", "--hide-scrollbars", `--remote-debugging-port=${port}`,
    `--user-data-dir=${mkdtempSync(join(tmpdir(), "linguini-export-"))}`, "about:blank",
  ], { stdio: "ignore" });

  try {
    let targets;
    for (let i = 0; i < 50 && !targets; i++) {
      try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); }
    }
    const ws = new WebSocket(targets.find(t => t.type === "page").webSocketDebuggerUrl);
    await new Promise(resolve => ws.addEventListener("open", resolve));
    let id = 0;
    const pending = new Map();
    ws.addEventListener("message", event => {
      const message = JSON.parse(event.data);
      if (pending.has(message.id)) { pending.get(message.id)(message); pending.delete(message.id); }
    });
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const next = ++id;
      pending.set(next, message => (message.error ? reject(new Error(`${method}: ${message.error.message}`)) : resolve(message.result)));
      ws.send(JSON.stringify({ id: next, method, params }));
    });
    /** Run an expression in the page and return its JSON value; promises are awaited. */
    const evaluate = async expression => {
      const { result, exceptionDetails } = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
      if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
      return result.value;
    };

    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: scale, mobile: false });
    await send("Page.enable");
    await send("Page.navigate", { url });
    await sleep(3000);
    return { send, evaluate, close: () => { ws.close(); proc.kill(); } };
  } catch (error) {
    proc.kill();
    throw error;
  }
}
