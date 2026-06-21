/**
 * extractor.js
 * Runs on job posting pages. Finds the job text using site-specific
 * selectors where known, falls back to a generic heuristic otherwise.
 * Does NOT send anything automatically; only responds when the popup
 * asks it to extract (user-initiated, not silent background scraping).
 */

function textOf(selector) {
  const el = document.querySelector(selector);
  return el ? el.innerText.trim() : null;
}

function extractLinkedIn() {
  return (
    textOf(".jobs-description__content") ||
    textOf(".jobs-box__html-content") ||
    textOf("#job-details")
  );
}

function extractIndeed() {
  return textOf("#jobDescriptionText");
}

function extractHandshake() {
  return (
    textOf("[data-hook='job-description']") ||
    textOf(".job-description")
  );
}

function extractGreenhouse() {
  return textOf("#content") || textOf(".job__description");
}

function extractLever() {
  return textOf(".posting-page") || textOf("[data-qa='job-description']");
}

function extractAshby() {
  return textOf("._descriptionText_kn8t4_146") || textOf("[class*='descriptionText']");
}

function extractWorkday() {
  return textOf("[data-automation-id='jobPostingDescription']");
}

function genericFallback() {
  // last resort: grab the largest text block on the page
  const candidates = Array.from(document.querySelectorAll("article, main, section, div"))
    .filter((el) => el.innerText && el.innerText.length > 300)
    .sort((a, b) => b.innerText.length - a.innerText.length);
  return candidates.length ? candidates[0].innerText.trim() : null;
}

function extractJobText() {
  const host = window.location.hostname;
  let text = null;
  let platform = "other";

  if (host.includes("linkedin.com")) {
    text = extractLinkedIn();
    platform = "linkedin";
  } else if (host.includes("indeed.com")) {
    text = extractIndeed();
    platform = "indeed";
  } else if (host.includes("joinhandshake.com")) {
    text = extractHandshake();
    platform = "handshake";
  } else if (host.includes("greenhouse.io")) {
    text = extractGreenhouse();
    platform = "greenhouse";
  } else if (host.includes("lever.co")) {
    text = extractLever();
    platform = "lever";
  } else if (host.includes("ashbyhq.com")) {
    text = extractAshby();
    platform = "ashby";
  } else if (host.includes("myworkdayjobs.com")) {
    text = extractWorkday();
    platform = "workday";
  }

  if (!text) {
    text = genericFallback();
  }

  return { text, platform, url: window.location.href };
}

// Listen for the popup asking for extraction (user clicked the button).
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "EXTRACT_JOB_TEXT") {
    sendResponse(extractJobText());
  }
});
