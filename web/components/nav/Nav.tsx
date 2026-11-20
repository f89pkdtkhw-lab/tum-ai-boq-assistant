"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./nav.module.css";

const LINKS = [
  { href: "/", label: "Upload & report" },
  { href: "/schritte", label: "Step reports" },
  { href: "/export", label: "Export" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className={styles.leiste} aria-label="Main">
      <ul className={styles.liste}>
        {LINKS.map(({ href, label }) => {
          const aktiv = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <li key={href}>
              <Link href={href} className={styles.link} aria-current={aktiv ? "page" : undefined}>
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
