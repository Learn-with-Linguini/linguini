"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { appLinks } from "@/lib/site";
import { Close, Menu } from "./icons";
import styles from "./SiteHeader.module.css";

const links = [
  { href: "/#try", label: "Try it" },
  { href: "/#features", label: "Features" },
  { href: "/#journal", label: "Journal" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/#faq", label: "FAQ" },
  { href: "/blog", label: "Blog" },
];

export function SiteHeader() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    const onResize = () => window.innerWidth > 880 && setOpen(false);
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onResize);
    };
  }, [open]);

  return (
    <header className={`${styles.header} ${scrolled || open ? styles.scrolled : ""}`}>
      <div className={`container ${styles.bar}`}>
        <Link href="/" className={styles.brand} aria-label="Linguini home">
          <Image src="/brand/linguini-wordmark.png" alt="Linguini" width={450} height={150} priority className={styles.wordmark} />
        </Link>

        <nav aria-label="Primary" className={styles.nav}>
          <ul className={styles.links}>
            {links.map(link => (
              <li key={link.href}>
                <a href={link.href} className={styles.link}>{link.label}</a>
              </li>
            ))}
          </ul>
        </nav>

        <div className={styles.actions}>
          <a href={appLinks.signIn} className={`btn-quiet ${styles.login}`}>Log in</a>
          <a href={appLinks.signUp} className="btn btn--small">Start free</a>
          <button
            type="button"
            className={styles.menuButton}
            aria-expanded={open}
            aria-controls="mobile-menu"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen(value => !value)}
          >
            {open ? <Close size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </div>

      <div id="mobile-menu" className={styles.sheet} data-open={open} hidden={!open}>
        <ul className="container">
          {links.map(link => (
            <li key={link.href}>
              <a href={link.href} onClick={() => setOpen(false)}>{link.label}</a>
            </li>
          ))}
          <li>
            <a href={appLinks.signIn} onClick={() => setOpen(false)}>Log in</a>
          </li>
        </ul>
      </div>
    </header>
  );
}
