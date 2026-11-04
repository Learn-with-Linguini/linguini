import type { AnchorHTMLAttributes } from "react";
import { Link as RouterLink, useLocation } from "react-router-dom";
import { isMarketingPath } from "../paths";
import { site } from "../lib/site";

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
};

export default function Link({ href, ...props }: LinkProps) {
  const location = useLocation();
  const destination = new URL(href, new URL(`${location.pathname}${location.search}`, site.url));
  const isInternalMarketingPath =
    destination.origin === site.url &&
    !href.includes("#") &&
    isMarketingPath(destination.pathname);

  if (isInternalMarketingPath) {
    return <RouterLink to={`${destination.pathname}${destination.search}${destination.hash}`} {...props} />;
  }

  return <a href={href} {...props} />;
}
