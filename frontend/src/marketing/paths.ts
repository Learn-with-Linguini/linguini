const marketingPathPatterns = [
  /^\/$/,
  /^\/blog(?:\/[^/]+)?\/?$/,
  /^\/learn\/[^/]+\/?$/,
  /^\/(?:privacy|terms|credits|share)\/?$/,
];

export function isMarketingPath(pathname: string): boolean {
  return marketingPathPatterns.some(pattern => pattern.test(pathname));
}
