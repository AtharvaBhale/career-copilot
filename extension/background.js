/**
 * background.js
 * Manifest V3 requires a service worker reference even for an extension
 * this simple. No persistent background work is needed; all logic lives
 * in the content script (extraction) and popup (sending), both of which
 * only run when the user actively interacts with the extension. This
 * file intentionally does nothing on its own, no silent scraping.
 */
