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

export const HelpIcon = ({ size = 22, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M9.6 9.6a2.5 2.5 0 1 1 3.2 2.4c-.6.2-.9.7-.9 1.3v.4M12 16.6v.2" />
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
