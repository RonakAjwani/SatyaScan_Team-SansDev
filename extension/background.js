// background.js

// Allows users to open the side panel by clicking the action toolbar icon
chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((error) => console.error(error));

// background.js

// Allows users to open the side panel by clicking the action toolbar icon
chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((error) => console.error(error));

chrome.action.onClicked.addListener((tab) => {
    // Fallback for some browser versions
    chrome.sidePanel.open({ windowId: tab.windowId });
});

chrome.runtime.onInstalled.addListener(() => {
    console.log("MisinfoDetector Copilot installed.");
    chrome.contextMenus.create({
        id: "verify-misinfo",
        title: "Verify with MisinfoDetector",
        contexts: ["selection"]
    });
});

chrome.runtime.onInstalled.addListener(() => {
    console.log("MisinfoDetector Copilot installed.");
});

// Handle Context Menu Click
chrome.contextMenus.onClicked.addListener((info, tab) => {
    if (info.menuItemId === "verify-misinfo" && info.selectionText) {
        // Open Side Panel
        chrome.sidePanel.open({ windowId: tab.windowId });

        // Wait a bit for the panel to load, then send the text
        setTimeout(() => {
            chrome.runtime.sendMessage({
                action: "ANALYZE_SELECTION",
                text: info.selectionText
            }).catch(err => console.log("Side panel not ready yet:", err));
        }, 500);
    }
});
