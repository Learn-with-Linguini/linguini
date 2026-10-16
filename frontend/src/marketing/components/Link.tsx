import type { AnchorHTMLAttributes } from "react";
import { Link as RouterLink } from "react-router-dom";
import { isMarketingPath } from "../paths";

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
};

export default function Link({ href, ...props }: LinkProps) {
  const destination = new URL(href, window.location.href);
  const isInternalMarketingPath =
    destination.origin === window.location.origin &&
    !href.includes("#") &&
    isMarketingPath(destination.pathname);

  if (isInternalMarketingPath) {
    return <RouterLink to={`${destination.pathname}${destination.search}${destination.hash}`} {...props} />;
  }

  return <a href={href} {...props} />;
}
