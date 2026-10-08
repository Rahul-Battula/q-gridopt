import type { ReactNode, SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 20, children, ...rest }: P & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconSun = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6" />
  </Svg>
);

export const IconWind = (p: P) => (
  <Svg {...p}>
    <path d="M12 12v9" />
    <path d="M12 12c0-3 .2-6 .2-8.5M12 12c2.6-1.5 5.2-2.7 7.4-3.4M12 12c-2.6-1.5-5.2-2.7-7.4-3.4" />
    <circle cx="12" cy="12" r="1.2" fill="currentColor" />
  </Svg>
);

export const IconFlame = (p: P) => (
  <Svg {...p}>
    <path d="M12 3c.6 3.2 4.5 5.1 4.5 9.4A4.5 4.5 0 0 1 12 17a4.5 4.5 0 0 1-4.5-4.6c0-1.7.8-2.9 1.7-3.9.2 1 .7 1.8 1.5 2.2C10.4 8 10.7 5.5 12 3Z" />
    <path d="M9 21h6" />
  </Svg>
);

export const IconBattery = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="7" width="16" height="10" rx="2.5" />
    <path d="M21.5 10.5v3" />
    <path d="M7 10.5v3M10.5 10.5v3M14 10.5v3" />
  </Svg>
);

export const IconCity = (p: P) => (
  <Svg {...p}>
    <path d="M4 21V9l6-3v15M10 21V4l9 4v13M3 21h18" />
    <path d="M13 11h3M13 14.5h3M7 12h.01M7 15.5h.01" />
  </Svg>
);

export const IconBolt = (p: P) => (
  <Svg {...p}>
    <path d="M13 2.5 5 13.2h5.5L10 21.5l8.5-11.2H13L13 2.5Z" />
  </Svg>
);

export const IconGrid = (p: P) => (
  <Svg {...p}>
    <rect x="3.5" y="3.5" width="7" height="7" rx="1.8" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="1.8" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="1.8" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="1.8" />
  </Svg>
);

export const IconAtom = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="1.6" fill="currentColor" />
    <ellipse cx="12" cy="12" rx="9.5" ry="3.9" />
    <ellipse cx="12" cy="12" rx="9.5" ry="3.9" transform="rotate(60 12 12)" />
    <ellipse cx="12" cy="12" rx="9.5" ry="3.9" transform="rotate(120 12 12)" />
  </Svg>
);

export const IconChip = (p: P) => (
  <Svg {...p}>
    <rect x="6" y="6" width="12" height="12" rx="2.2" />
    <rect x="9.5" y="9.5" width="5" height="5" rx="1" />
    <path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3" />
  </Svg>
);

export const IconList = (p: P) => (
  <Svg {...p}>
    <path d="M8.5 6.5h12M8.5 12h12M8.5 17.5h12" />
    <circle cx="4.5" cy="6.5" r="1" fill="currentColor" />
    <circle cx="4.5" cy="12" r="1" fill="currentColor" />
    <circle cx="4.5" cy="17.5" r="1" fill="currentColor" />
  </Svg>
);

export const IconBars = (p: P) => (
  <Svg {...p}>
    <path d="M5 20V11M12 20V4M19 20v-6" />
  </Svg>
);

export const IconCheck = (p: P) => (
  <Svg {...p}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Svg>
);

export const IconArrow = (p: P) => (
  <Svg {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Svg>
);

export const IconShield = (p: P) => (
  <Svg {...p}>
    <path d="M12 3 5 6v5.5c0 4.4 2.8 7.6 7 9.5 4.2-1.9 7-5.1 7-9.5V6l-7-3Z" />
    <path d="m9 12 2.2 2.2L15.5 10" />
  </Svg>
);

/** Bloch sphere: the standard picture of one qubit's state. */
export const IconBloch = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <ellipse cx="12" cy="12" rx="8.5" ry="3" strokeDasharray="2 2.2" />
    <path d="M12 3.5v17" strokeDasharray="1.5 2" />
    <path d="M12 12 17.5 6.8" />
    <circle cx="17.5" cy="6.8" r="1.3" fill="currentColor" />
    <path d="M12 2v1.5M12 20.5V22" />
  </Svg>
);

/** A quantum-circuit wire with one gate. */
export const IconGate = (p: P) => (
  <Svg {...p}>
    <path d="M2.5 12h4M13.5 12h8" />
    <rect x="6.5" y="8" width="7" height="8" rx="1.2" />
    <path d="M9.2 10.7h2.2l-2.2 2.6h2.2" strokeWidth={1.4} />
  </Svg>
);

/** Probability wave. */
export const IconWave = (p: P) => (
  <Svg {...p}>
    <path d="M2 12c2-7 4-7 6 0s4 7 6 0 4-7 6 0" />
  </Svg>
);
