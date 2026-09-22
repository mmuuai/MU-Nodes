// Cache-busted loader for the updated text viewer implementation.
// ComfyUI discovers every file in web/js; the query forces browsers to fetch
// the current implementation instead of reusing the old module cache.
import "./text_viewer_v1.js?rev=20260922-14";
