/**
 * Extract database name from URL path like /$DATABASE/-/ca460/...
 */
export function getDatabaseFromUrl(): string {
  const path = window.location.pathname;
  const match = path.match(/^\/([^\/]+)\/-\/ca460/);
  return match ? match[1] : 'tmp'; // fallback to 'tmp' if not found
}