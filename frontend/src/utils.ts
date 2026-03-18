/**
 * Extract database name from URL path like /$DATABASE/-/ca460/...
 */
export function getDatabaseFromUrl(): string {
  const path = window.location.pathname;
  const match = path.match(/^\/([^\/]+)\/-\/ca460/);
  return match ? match[1] : 'tmp';
}

/**
 * Extract document ID from URL path like /$DATABASE/-/ca460/document/123
 */
export function getDocumentIdFromUrl(): string {
  const path = window.location.pathname;
  const match = path.match(/\/-\/ca460\/document\/(\d+)/);
  return match ? match[1] : '';
}

/**
 * Extract page number from URL path like /$DATABASE/-/ca460/document/123/page/4
 */
export function getPageNumberFromUrl(): number {
  const path = window.location.pathname;
  const match = path.match(/\/-\/ca460\/document\/\d+\/page\/(\d+)/);
  return match ? parseInt(match[1], 10) : 1;
}