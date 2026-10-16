import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 20, children, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

export const ArrowRight = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12h13" />
    <path d="m13 6 6 6-6 6" />
  </Icon>
);

export const ArrowLeft = (p: IconProps) => (
  <Icon {...p}>
    <path d="M19 12H6" />
    <path d="m11 6-6 6 6 6" />
  </Icon>
);

export const Check = (p: IconProps) => (
  <Icon {...p}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Icon>
);

export const Close = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Icon>
);

export const Plus = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);

export const Menu = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 7h16M4 12h16M4 17h10" />
  </Icon>
);

export const Speaker = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5H4Z" />
    <path d="M15.5 9a4 4 0 0 1 0 6" />
    <path d="M18 6.5a7.5 7.5 0 0 1 0 11" />
  </Icon>
);

export const SpeakerOff = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5H4Z" />
    <path d="m16 9.5 5 5M21 9.5l-5 5" />
  </Icon>
);

export const Mic = (p: IconProps) => (
  <Icon {...p}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5.5 11a6.5 6.5 0 0 0 13 0" />
    <path d="M12 17.5V21" />
  </Icon>
);

export const Camera = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2.2l1.5-2h5.6l1.5 2h2.2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5v-9Z" />
    <circle cx="12" cy="13" r="3.4" />
  </Icon>
);

export const Book = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 6.5C10.3 5.2 7.9 4.7 4.5 5v13c3.4-.3 5.8.2 7.5 1.5 1.7-1.3 4.1-1.8 7.5-1.5V5c-3.4-.3-5.8.2-7.5 1.5Z" />
    <path d="M12 6.5v13" />
  </Icon>
);

export const Refresh = (p: IconProps) => (
  <Icon {...p}>
    <path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" />
    <path d="M19.5 4.5v4h-4" />
  </Icon>
);

export const ChevronDown = (p: IconProps) => (
  <Icon {...p}>
    <path d="m6 9.5 6 6 6-6" />
  </Icon>
);

export const Eye = (p: IconProps) => (
  <Icon {...p}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
    <circle cx="12" cy="12" r="2.8" />
  </Icon>
);

export const Download = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 4v11" />
    <path d="m7 10.5 5 5 5-5" />
    <path d="M5 19.5h14" />
  </Icon>
);

export const Sparkle = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3.5c.6 3.9 2.6 5.9 6.5 6.5-3.9.6-5.9 2.6-6.5 6.5-.6-3.9-2.6-5.9-6.5-6.5 3.9-.6 5.9-2.6 6.5-6.5Z" />
    <path d="M18.5 16.5v4M16.5 18.5h4" />
  </Icon>
);

export const Database = (p: IconProps) => (
  <Icon {...p}>
    <ellipse cx="12" cy="6" rx="7" ry="2.5" />
    <path d="M5 6v12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V6" />
    <path d="M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" />
  </Icon>
);

export const Cloud = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7.5 18.5a4 4 0 0 1-.6-8 5.5 5.5 0 0 1 10.6 1.3 3.4 3.4 0 0 1-.5 6.7H7.5Z" />
  </Icon>
);

export const Card = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="6" width="17" height="12" rx="2" />
    <path d="M3.5 10h17M7 14.5h3" />
  </Icon>
);

export const Users = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="9" cy="8.5" r="3" />
    <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
    <path d="M15.5 5.8a3 3 0 0 1 0 5.4M17.5 14a5.5 5.5 0 0 1 3 5" />
  </Icon>
);

export const Megaphone = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 10v4h3l8 4.5v-13L7 10H4Z" />
    <path d="M7 14l1.5 5h2.5l-1.3-4.3" />
    <path d="M18.5 9.5a3.5 3.5 0 0 1 0 5" />
  </Icon>
);

export const Coins = (p: IconProps) => (
  <Icon {...p}>
    <ellipse cx="9" cy="7" rx="5" ry="2.5" />
    <path d="M4 7v4c0 1.4 2.2 2.5 5 2.5s5-1.1 5-2.5V7" />
    <path d="M10 16.2c.6 1.3 2.7 2.3 5 2.3 2.8 0 5-1.1 5-2.5v-4c0-1.3-2-2.4-4.6-2.5" />
  </Icon>
);

export const Flame = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 21c3.6 0 6-2.4 6-5.6 0-3.9-3.3-5.9-4.2-10.4C11 7 9.5 9.2 9.3 11.3 8.3 10.6 7.8 9.4 7.8 8.3 6.6 9.8 6 11.6 6 13.4 6 18.6 8.4 21 12 21Z" />
  </Icon>
);

export const Layers = (p: IconProps) => (
  <Icon {...p}>
    <path d="m12 4 8.5 4.5L12 13 3.5 8.5 12 4Z" />
    <path d="m3.5 12.5 8.5 4.5 8.5-4.5" />
    <path d="m3.5 16.5 8.5 4.5 8.5-4.5" />
  </Icon>
);

export const Gauge = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4.5 17a8 8 0 1 1 15 0" />
    <path d="m12 13 3.5-4" />
    <circle cx="12" cy="13" r="1.2" />
  </Icon>
);

export const Share = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="6.5" cy="12" r="2.5" />
    <circle cx="17.5" cy="6" r="2.5" />
    <circle cx="17.5" cy="18" r="2.5" />
    <path d="m8.7 10.8 6.6-3.6M8.7 13.2l6.6 3.6" />
  </Icon>
);
