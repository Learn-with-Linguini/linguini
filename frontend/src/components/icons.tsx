type IconProps = {
  size?: number;
  className?: string;
};

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
});

export const HomeIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4v-5h-6v5H5a1 1 0 0 1-1-1z" />
  </svg>
);

export const EyeIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

export const CameraIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M3 8.5h3.5L8 6h8l1.5 2.5H21V19H3z" />
    <circle cx="12" cy="13" r="3.2" />
  </svg>
);

export const BookIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4 5h6a2 2 0 0 1 2 2v12a2 2 0 0 0-2-2H4z" />
    <path d="M20 5h-6a2 2 0 0 0-2 2v12a2 2 0 0 1 2-2h6z" />
  </svg>
);

export const JournalIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M6 4h11a2 2 0 0 1 2 2v14H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" />
    <path d="M8 4v16M11 8h5M11 12h4" />
    <path d="m12 17 4.8-4.8 1.8 1.8-4.8 4.8-2.3.5z" />
  </svg>
);

export const TrendIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4 15.5 9 10l3.5 3.5L20 6" />
    <path d="M20 10V6h-4" />
  </svg>
);

export const PersonIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="8.5" r="3.6" />
    <path d="M5 20c1.2-3.6 4-5.2 7-5.2S17.8 16.4 19 20" />
  </svg>
);

export const MicIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" />
  </svg>
);

export const SpeakerIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M5 9.5h3l4-3v11l-4-3H5z" />
    <path d="M16 9.2a4 4 0 0 1 0 5.6" />
  </svg>
);

export const ArrowRightIcon = ({ size = 20, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4 12h15M14 7l5 5-5 5" />
  </svg>
);

export const ArrowLeftIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
  <path d="M20 12H5M10 7l-5 5 5 5" />
  </svg>
);

export const ChevronLeftIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="m15 18-6-6 6-6" />
  </svg>
);

export const ChevronRightIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="m9 18 6-6-6-6" />
  </svg>
);

export const ChevronDownIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="m6 9 6 6 6-6" />
  </svg>
);

export const CheckIcon = ({ size = 20, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M5 12.5 10 17l9-10" />
  </svg>
);

export const CloseIcon = ({ size = 20, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="m7 7 10 10M17 7 7 17" />
  </svg>
);

export const MarkerIcon = ({ size = 20, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="3" />
    <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
  </svg>
);

export const HelpIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M9.6 9.6a2.5 2.5 0 1 1 3.2 2.4c-.6.2-.9.7-.9 1.3v.4M12 16.6v.2" />
  </svg>
);

export const CountIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="6" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="18" cy="12" r="2" />
  </svg>
);

export const HandIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M7 11V7.5a1.5 1.5 0 0 1 3 0V10M10 9V5.5a1.5 1.5 0 0 1 3 0V10M13 9V6.5a1.5 1.5 0 0 1 3 0V11M16 10a1.5 1.5 0 0 1 3 0v4c0 4-2.5 6-6 6h-1c-2.2 0-3.6-1-4.8-2.6L4.5 14a1.5 1.5 0 0 1 2.3-1.9L9 14" />
  </svg>
);

export const HeartIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M20.5 8.8c0 4.5-8.5 10-8.5 10s-8.5-5.5-8.5-10A4.3 4.3 0 0 1 12 7.5a4.3 4.3 0 0 1 8.5 1.3z" />
  </svg>
);

export const ChatIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4 5h12a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3H9l-4 3v-3H4a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3z" />
    <path d="M6 9h8M6 12h5" />
  </svg>
);

export const PlusIcon = ({ size = 20, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);

export const FarfalleIcon = ({ size = 28, className }: IconProps) => (
  <svg {...base(size)} className={className} viewBox="0 0 32 32">
    <path
      d="M4 6c4 0 7.1 2.7 9.4 6h5.2C20.9 8.7 24 6 28 6v20c-4 0-7.1-2.7-9.4-6h-5.2C11.1 23.3 8 26 4 26z"
      fill="currentColor"
      stroke="currentColor"
      strokeWidth="1.4"
    />
    <path d="M13.4 12h5.2v8h-5.2z" fill="#fffdf8" stroke="none" />
  </svg>
);

export const UploadIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M12 16V5M8 9l4-4 4 4" />
    <path d="M5 16v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2" />
  </svg>
);

export const FilterIcon = ({ size = 20, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4 6h16M7 12h10M10 18h4" />
  </svg>
);

export const PlayIcon = ({ size = 20, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M8 5.5 18 12 8 18.5z" />
  </svg>
);

export const BasilIcon = ({ size = 20, className }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" className={className} aria-hidden="true">
    <path d="M20 3C9 2 3 7 5 14c2 7 13 5 15-11Z" fill="currentColor" stroke="none" />
    <path d="m3 21 12-12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

export const LinkedInIcon = ({ size = 20, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
    <rect x="2" y="9" width="4" height="12" />
    <circle cx="4" cy="4" r="2" />
  </svg>
);

export const InstagramIcon = ({ size = 20, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
    <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
    <line x1="17.5" y1="6.5" x2="17.51" y2="6.5" />
  </svg>
);

export const XIcon = ({ size = 20, className }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
    aria-hidden="true"
  >
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
  </svg>
);

export const TikTokIcon = ({ size = 20, className }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
    aria-hidden="true"
  >
    <path d="M19.589 6.686a4.793 4.793 0 0 1-3.77-4.245V2h-3.445v13.672a2.896 2.896 0 0 1-5.201 1.743l-.068-.102a2.895 2.895 0 0 1 3.18-4.321V9.45a6.34 6.34 0 0 0-5.165 1.554 6.34 6.34 0 0 0-1.87 4.542 6.34 6.34 0 0 0 8.04 6.069 6.34 6.34 0 0 0 4.529-6.069V9.404a8.232 8.232 0 0 0 5.21 1.83v-3.48a4.8 4.8 0 0 1-1.44-.068z" />
  </svg>
);
