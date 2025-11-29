// content.js

// content.js

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "SCAN_PAGE") {
        const result = scanPage();
        sendResponse(result);
    }
    return true;
});

function scanPage() {
    const clone = document.body.cloneNode(true);

    // 1. Clean Noise
    const noise = [
        'script', 'style', 'noscript', 'iframe', 'svg', 'nav', 'footer', 'header', 'aside',
        '.ad', '.ads', '.advertisement', '.social-share', '.comments', '.sidebar', '.related-content',
        '[role="alert"]', '[role="banner"]', '[role="navigation"]', '[aria-hidden="true"]'
    ];
    noise.forEach(s => clone.querySelectorAll(s).forEach(el => el.remove()));

    // 2. Extract Main Text (Readability-lite)
    const content = extractText(clone);

    // 3. Extract Main Image
    const mainImage = extractMainImage();

    // 4. Extract Headline
    const headline = extractHeadline(clone);

    // 5. Extract Embedded X Posts
    const embeddedTweets = extractEmbeddedTweets(document);

    return { content, mainImage, headline, embeddedTweets };
}

function extractEmbeddedTweets(root) {
    const tweets = [];

    // 1. Blockquote embeds (standard)
    root.querySelectorAll('blockquote.twitter-tweet a').forEach(a => {
        const href = a.href;
        if (href.includes('twitter.com') || href.includes('x.com')) {
            if (href.includes('/status/')) {
                tweets.push(href);
            }
        }
    });

    // 2. Iframe embeds
    root.querySelectorAll('iframe').forEach(iframe => {
        try {
            const src = iframe.src;
            if (src.includes('platform.twitter.com/embed')) {
                // Extract tweet ID from query params if possible, or just note it
                // Usually the iframe src has 'id' parameter
                const urlParams = new URLSearchParams(new URL(src).search);
                const tweetId = urlParams.get('id');
                if (tweetId) {
                    tweets.push(`https://x.com/i/status/${tweetId}`);
                }
            }
        } catch (e) {
            // Ignore cross-origin issues
        }
    });

    // Deduplicate
    return [...new Set(tweets)];
}

function extractHeadline(root) {
    const h1 = root.querySelector('h1');
    if (h1 && h1.innerText.length > 5) return h1.innerText.trim();

    const ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle && ogTitle.content) return ogTitle.content.trim();

    return document.title.trim();
}

function extractText(root) {
    // Candidates: p, div, article, section
    const candidates = root.querySelectorAll('p, div, article, section');
    let bestCandidate = null;
    let maxScore = 0;

    candidates.forEach(node => {
        const text = node.innerText.trim();
        if (text.length < 100) return; // Too short

        // Scoring Heuristics
        let score = 0;

        // Base: Text Length
        score += text.length * 0.5;

        // Reward: Punctuation (indicates natural language sentences)
        const commas = (text.match(/,/g) || []).length;
        const periods = (text.match(/\./g) || []).length;
        score += (commas + periods) * 5;

        // Penalty: Link Density (Navigation/Lists are mostly links)
        const linkTextLength = Array.from(node.querySelectorAll('a'))
            .reduce((acc, a) => acc + a.innerText.length, 0);

        if (linkTextLength > 0) {
            const linkDensity = linkTextLength / text.length;
            if (linkDensity > 0.5) score -= 1000; // Heavy penalty for link farms
            else score -= linkDensity * 200;
        }

        // Boost: Semantic Tags
        if (node.tagName === 'ARTICLE') score += 500;
        if (node.className.includes('article') || node.className.includes('content')) score += 200;

        if (score > maxScore) {
            maxScore = score;
            bestCandidate = node;
        }
    });

    if (bestCandidate) {
        return bestCandidate.innerText.replace(/\s+/g, ' ').trim();
    }

    // Fallback: Cleaned Body Text
    return root.innerText.replace(/\s+/g, ' ').trim();
}

function extractMainImage() {
    // 1. Best Source: Open Graph Meta Tag
    const ogImage = document.querySelector('meta[property="og:image"]');
    if (ogImage && ogImage.content) {
        return ogImage.content;
    }

    // 2. Fallback: Find largest image in the body
    const images = document.querySelectorAll('img');
    let bestImg = null;
    let maxArea = 0;

    images.forEach(img => {
        // Skip small icons/ads
        if (img.width < 200 || img.height < 150) return;

        const area = img.width * img.height;
        if (area > maxArea) {
            maxArea = area;
            bestImg = img.src;
        }
    });

    return bestImg;
}
