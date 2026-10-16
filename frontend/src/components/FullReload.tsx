import { useEffect } from "react";
import { useLocation } from "react-router-dom";

export function FullReload() {
  const { pathname, search, hash } = useLocation();

  useEffect(() => {
    window.location.replace(`${pathname}${search}${hash}`);
  }, [pathname, search, hash]);

  return null;
}
