/* Extracted from templates/indicator.html so the Content-Security-Policy can forbid inline scripts. */
'use strict';
const source = document.getElementById("pine-source").textContent;
const status = document.getElementById("copy-status");

// download payload is built from the rendered text — keeps the download and
// the displayed block byte-identical
const dl = document.getElementById("download-button");
dl.setAttribute("href", "data:text/plain;charset=utf-8," + encodeURIComponent(source));

document.getElementById("copy-button").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(source);
    status.textContent = "Copied " + source.length.toLocaleString() + " characters — paste it straight into the Pine Editor.";
  } catch (error) {
    // Clipboard API can be denied (http origins / older browsers): fall back
    // to a manual selection so the member can still Ctrl+C easily.
    const range = document.createRange();
    range.selectNodeContents(document.getElementById("pine-source"));
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    status.textContent = "Script selected — press Ctrl+C to copy.";
    status.style.color = "#ffd166";
  }
  setTimeout(() => { status.textContent = ""; status.style.color = "#4ce08d"; }, 6000);
});
