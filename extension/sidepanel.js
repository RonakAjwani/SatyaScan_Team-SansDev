// sidepanel.js

const scanBtn = document.getElementById("scanBtn");
const resetBtn = document.getElementById("resetBtn");
const chatContainer = document.getElementById("chatContainer");

// Image Elements
const fileInput = document.getElementById("fileInput");
const dropZone = document.getElementById("dropZone");
const previewImg = document.getElementById("preview-img");
const imagePreview = document.getElementById("image-preview");
const analyzeImageBtn = document.getElementById("analyzeImageBtn");
const resetImageBtn = document.getElementById("resetImageBtn");

// History & Settings Elements
const historyList = document.getElementById("history-list");
const clearHistoryBtn = document.getElementById("clearHistoryBtn");
const themeToggle = document.getElementById("themeToggle");

// API Endpoint
const API_URL = "http://localhost:8000/api/analyze";

// --- Initialization ---
document.addEventListener("DOMContentLoaded", () => {
  loadSettings(); // Load all settings including theme
  loadHistory();

  // Auto-scan check
  const autoScan = localStorage.getItem("autoScan") === "true";
  if (autoScan) {
    // Small delay to ensure tab is ready
    setTimeout(() => scanBtn.click(), 500);
  }
});

// --- Tab Switching Logic ---
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document
      .querySelectorAll(".tab")
      .forEach((t) => t.classList.remove("active"));
    document
      .querySelectorAll(".tab-content")
      .forEach((c) => c.classList.remove("active"));

    tab.classList.add("active");
    const tabId = tab.getAttribute("data-tab");
    document.getElementById(`${tabId}-tab`).classList.add("active");
  });
});

// --- Settings Logic ---
const autoScanToggle = document.getElementById("autoScanToggle");
const confidenceThreshold = document.getElementById("confidenceThreshold");
const thresholdValue = document.getElementById("thresholdValue");

themeToggle.addEventListener("change", (e) => {
  const theme = e.target.checked ? "dark" : "light";
  setTheme(theme);
});

autoScanToggle.addEventListener("change", (e) => {
  localStorage.setItem("autoScan", e.target.checked);
});

confidenceThreshold.addEventListener("input", (e) => {
  thresholdValue.textContent = e.target.value + "%";
  localStorage.setItem("confidenceThreshold", e.target.value);
});

function setTheme(theme) {
  if (theme === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
    themeToggle.checked = true;
  } else {
    document.documentElement.removeAttribute("data-theme");
    themeToggle.checked = false;
  }
  localStorage.setItem("theme", theme);
}

function loadSettings() {
  // Theme
  const savedTheme = localStorage.getItem("theme") || "dark";
  setTheme(savedTheme);

  // Auto Scan
  const autoScan = localStorage.getItem("autoScan") === "true";
  autoScanToggle.checked = autoScan;

  // Threshold
  const savedThreshold = localStorage.getItem("confidenceThreshold") || "70";
  confidenceThreshold.value = savedThreshold;
  thresholdValue.textContent = savedThreshold + "%";
}

// --- History Logic ---
async function saveHistory(item) {
  const { history = [] } = await chrome.storage.local.get("history");
  // Add new item to beginning
  const newItem = {
    id: Date.now(),
    timestamp: new Date().toLocaleString(),
    ...item,
  };
  const newHistory = [newItem, ...history].slice(0, 50); // Keep last 50
  await chrome.storage.local.set({ history: newHistory });
  loadHistory(); // Refresh list
}

async function loadHistory() {
  const { history = [] } = await chrome.storage.local.get("history");
  historyList.innerHTML = "";

  if (history.length === 0) {
    historyList.innerHTML =
      '<div style="text-align: center; color: var(--text-secondary); margin-top: 2rem;">No history yet.</div>';
    return;
  }

  history.forEach((item) => {
    const div = document.createElement("div");
    div.className = "history-item";
    div.innerHTML = `
            <div class="history-meta">
                <span>${item.type === "image" ? "Image Scan" : "Page Scan"
      }</span>
                <span>${item.timestamp}</span>
            </div>
            <div class="history-preview">
                ${item.previewText}
            </div>
            <div class="verdict-badge ${item.verdict ? "verdict-false" : "verdict-true"
      }" style="margin-top: 0.5rem; font-size: 0.6rem;">
                ${item.verdict ? "MISINFO" : "VERIFIED"}
            </div>
        `;
    div.addEventListener("click", () => restoreHistory(item));
    historyList.appendChild(div);
  });
}

function restoreHistory(item) {
  // Switch to Scan tab
  document.querySelector('[data-tab="scan"]').click();

  // Clear current view
  chatContainer.innerHTML = "";

  // Add User Message
  addMessage(
    "user",
    `Restored Scan: "${item.previewText.substring(0, 50)}..."`
  );

  // Add Result
  displayResult(item.result, false); // false = don't save to history again
}

clearHistoryBtn.addEventListener("click", async () => {
  if (confirm("Are you sure you want to clear all history?")) {
    await chrome.storage.local.set({ history: [] });
    loadHistory();
  }
});

// --- Context Menu Listener ---
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "ANALYZE_SELECTION" && request.text) {
    document.querySelector('[data-tab="scan"]').click();
    analyzeText(request.text);
  }
});

// --- Scan Page Logic ---
// --- Scan Page Logic ---
scanBtn.addEventListener("click", async () => {
  try {
    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true,
    });

    if (!tab) throw new Error("No active tab found.");

    // Check for restricted URLs
    if (tab.url && (tab.url.startsWith("chrome://") || tab.url.startsWith("edge://") || tab.url.startsWith("about:"))) {
      addMessage("agent", "Cannot scan browser system pages. Please navigate to a website.");
      return;
    }

    let response;
    try {
      // Try sending message first
      response = await chrome.tabs.sendMessage(tab.id, { action: "SCAN_PAGE" });
    } catch (e) {
      // If failed, try injecting script
      console.log("Connection failed, attempting injection...", e);
      addMessage("agent", "Initializing scanner on this page...");

      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content.js"]
      });

      // Wait a moment for script to initialize
      await new Promise(r => setTimeout(r, 500));

      // Retry message
      response = await chrome.tabs.sendMessage(tab.id, { action: "SCAN_PAGE" });
    }

    if (!response || !response.content || response.content.length < 50) {
      addMessage(
        "agent",
        'Could not automatically extract enough text from this page. Please <b>highlight the text</b> you want to verify, right-click, and select "Verify with MisinfoDetector".'
      );
      return;
    }

    // Pass text, image, headline, and embedded tweets
    analyzeText(
      response.content.substring(0, 5000),
      response.mainImage,
      response.headline,
      response.embeddedTweets
    );
  } catch (error) {
    console.error(error);
    addMessage("agent", `Error: Could not connect to page. Try refreshing the tab.`);
  }
});

const chooseFileBtn = document.getElementById("chooseFileBtn");

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.style.borderColor = "var(--accent-primary)";
});

dropZone.addEventListener("dragleave", () => {
  dropZone.style.borderColor = "var(--glass-border)";
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.style.borderColor = "var(--glass-border)";
  if (e.dataTransfer.files.length) handleImage(e.dataTransfer.files[0]);
});

dropZone.addEventListener("click", () => {
  fileInput.click();
});

chooseFileBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  fileInput.click();
});

fileInput.addEventListener("change", (e) => {
  if (e.target.files.length) handleImage(e.target.files[0]);
});

function handleImage(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    previewImg.src = e.target.result;
    dropZone.style.display = "none";
    imagePreview.style.display = "block";
  };
  reader.readAsDataURL(file);
}

resetImageBtn.addEventListener("click", () => {
  fileInput.value = "";
  previewImg.src = "";
  imagePreview.style.display = "none";
  dropZone.style.display = "flex";
});

analyzeImageBtn.addEventListener("click", async () => {
  document.querySelector('[data-tab="scan"]').click();

  const base64Response = await fetch(previewImg.src);
  const blob = await base64Response.blob();

  analyzeImage(blob);
});

async function analyzeImage(imageBlob) {
  addMessage("user", "Analyzing uploaded image...");

  try {
    const thinkingId = showThinking();

    const formData = new FormData();
    formData.append("file", imageBlob, "upload.png");

    const apiRes = await fetch(API_URL, { method: "POST", body: formData });
    if (!apiRes.ok) throw new Error("Backend analysis failed.");
    const result = await apiRes.json();

    stopThinking(thinkingId);
    displayResult(result, true, "image", "Image Analysis");
  } catch (error) {
    addMessage("agent", `Error: ${error.message}`);
  }
}

// --- Shared Analysis Logic ---
async function analyzeText(
  text,
  imageUrl = null,
  headline = null,
  embeddedTweets = []
) {
  // Determine Display Message
  let displayMsg = "Analyzing Page Content...";

  if (headline) {
    displayMsg = `Analyzing: "<b>${headline}</b>"`;
  } else if (text) {
    // If no headline (e.g. selection), show snippet
    displayMsg = `Analyzing: "${text.substring(0, 60)}..."`;
  }

  addMessage("user", displayMsg, true);

  if (imageUrl) {
    addMessage(
      "user",
      `<img src="${imageUrl}" style="max-width: 100%; border-radius: 8px; margin-top: 0.5rem;" alt="Scanned Image">`,
      true
    );
    addMessage("user", `Found relevant image. Scanning for AI generation...`);
  }

  if (embeddedTweets && embeddedTweets.length > 0) {
    addMessage(
      "user",
      `Found ${embeddedTweets.length} embedded X post(s). Analyzing context...`
    );
  }

  scanBtn.disabled = true;
  scanBtn.innerHTML = "Scanning...";

  try {
    const thinkingId = showThinking();

    const formData = new FormData();
    formData.append("text", text);
    if (imageUrl) {
      formData.append("image_url", imageUrl);
    }
    if (embeddedTweets && embeddedTweets.length > 0) {
      embeddedTweets.forEach((url) => formData.append("embedded_tweets", url));
    }

    const apiRes = await fetch(API_URL, { method: "POST", body: formData });
    if (!apiRes.ok) throw new Error("Backend analysis failed.");
    const result = await apiRes.json();

    stopThinking(thinkingId);

    // Use headline for history preview if available
    const preview = headline ? headline : text.substring(0, 100);
    displayResult(result, true, "text", preview);
  } catch (error) {
    addMessage("agent", `Error: ${error.message}`);
  } finally {
    scanBtn.disabled = false;
    scanBtn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
      Scan Page
    `;
  }
}

// --- Helper Functions ---
function showThinking() {
  const thinkingId = "thinking-" + Date.now();
  const thinkingHtml = `
    <div class="thinking-container" id="${thinkingId}">
      <div class="thinking-dots">
        <div class="dot"></div><div class="dot"></div><div class="dot"></div>
      </div>
      <span id="agent-status-${thinkingId}">Initializing Agents...</span>
    </div>
  `;
  addMessage("agent", thinkingHtml, true);

  const steps = [
    "Extracting Claims...",
    "Searching Web...",
    "Verifying Evidence...",
    "Drafting Report...",
  ];
  let i = 0;
  const interval = setInterval(() => {
    const span = document.getElementById(`agent - status - ${thinkingId} `);
    if (span) span.textContent = steps[i++ % steps.length];
  }, 2500);

  return { id: thinkingId, interval };
}

function stopThinking(thinkingObj) {
  clearInterval(thinkingObj.interval);
  const el = document.getElementById(thinkingObj.id);
  if (el) el.closest(".message").remove();
}

function addMessage(role, content, isHtml = false) {
  const div = document.createElement("div");
  div.className = `message ${role} `;
  isHtml ? (div.innerHTML = content) : (div.textContent = content);
  chatContainer.appendChild(div);
  chatContainer.scrollTop = chatContainer.scrollHeight;
  return div;
}

function displayResult(
  result,
  saveToHistory = true,
  type = "text",
  previewText = ""
) {
  const { verdict, confidence, report, citations } = result;
  const isMisinfo =
    verdict === true || verdict === "FAKE" || verdict === "MANIPULATED";

  let badgeClass = "verdict-true";
  let badgeText = "VERIFIED / LIKELY TRUE";

  const threshold = parseInt(
    localStorage.getItem("confidenceThreshold") || "70"
  );

  if (verdict === true || verdict === "FAKE") {
    badgeClass = "verdict-false";
    badgeText = "MISINFORMATION / FAKE";
  } else if (verdict === "MANIPULATED") {
    badgeClass = "verdict-false"; // Or a warning color
    badgeText = "MANIPULATED IMAGE";
  } else if (verdict === "REAL" || verdict === false) {
    // Check threshold for "Verified"
    if (confidence >= threshold) {
      badgeClass = "verdict-true";
      badgeText = "VERIFIED / LIKELY AUTHENTIC";
    } else {
      badgeClass = "verdict-true"; // Keep green but change text? Or make it yellow/neutral?
      // Let's make it neutral
      badgeClass = "verdict-true";
      badgeText = `LIKELY AUTHENTIC (Low Confidence < ${threshold}%)`;
      // Or maybe just "UNVERIFIED"
    }
  } else if (verdict === "UNKNOWN") {
    badgeClass = "verdict-true"; // Neutral
    badgeText = "UNVERIFIED";
  }

  // Save to History
  if (saveToHistory) {
    saveHistory({
      type,
      previewText,
      verdict:
        verdict === true || verdict === "FAKE" || verdict === "MANIPULATED",
      result,
    });
  }

  // Render Citations Chips
  let citationsHtml = "";
  if (citations && citations.length > 0) {
    citationsHtml =
      '<div class="citation-list">' +
      citations
        .map((url, index) => {
          try {
            const hostname = new URL(url).hostname.replace("www.", "");
            return `<a href="${url}" target="_blank" class="citation-chip" title="${url}">${index + 1
              }. ${hostname}</a>`;
          } catch (e) {
            return "";
          }
        })
        .join("") +
      "</div>";
  }

  // Helper to format text with links
  const formatReportText = (text, citations) => {
    if (!text) return "";
    let formatted = text.replace(/\n/g, "<br>");
    if (citations) {
      citations.forEach((url, index) => {
        const escapedUrl = url.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const regex = new RegExp(escapedUrl, "g");
        formatted = formatted.replace(
          regex,
          ` <a href="${url}" target="_blank" style="color: var(--accent-primary); text-decoration: none;">[Source ${index + 1
          }]</a>`
        );
      });
    }
    return formatted;
  };

  let contentHtml = "";

  if (result.image_report || result.text_report) {
    // New Split Structure
    if (result.image_report) {
      contentHtml += `
            <div class="report-section" style="margin-bottom: 1rem; padding-bottom: 1rem; border-bottom: 1px solid var(--glass-border);">
                <h3 style="margin: 0 0 0.5rem 0; font-size: 0.95rem; color: var(--accent-primary); display: flex; align-items: center; gap: 0.5rem;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
                    Image Analysis
                </h3>
                <div style="line-height: 1.6; font-size: 0.9rem;">${formatReportText(
        result.image_report,
        citations
      )}</div>
            </div>
          `;
    }
    if (result.text_report) {
      contentHtml += `
            <div class="report-section">
                <h3 style="margin: 0 0 0.5rem 0; font-size: 0.95rem; color: var(--accent-primary); display: flex; align-items: center; gap: 0.5rem;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                    Content Verification
                </h3>
                <div style="line-height: 1.6; font-size: 0.9rem;">${formatReportText(
        result.text_report,
        citations
      )}</div>
            </div>
          `;
    }
  } else {
    // Legacy Fallback
    contentHtml = `<div style="line-height: 1.6;">${formatReportText(
      report,
      citations
    )}</div>`;
  }

  const html = `
    <div class="verdict-badge ${badgeClass}">${badgeText}</div>
    ${contentHtml}
    ${citationsHtml}
    <div style="margin-top: 0.5rem; font-size: 0.8rem; color: var(--text-secondary);">
      Confidence: ${confidence}%
      <div class="confidence-bar">
        <div class="confidence-fill" style="width: ${confidence}%; background: ${isMisinfo ? "var(--danger)" : "var(--success)"
    }"></div>
      </div>
    </div>
  `;

  addMessage("agent", html, true);
}
