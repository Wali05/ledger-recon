// Ledger Recon's own icon set: 24px grid, 1.6px round strokes, currentColor.
// Drawn for this app so every glyph shares one weight and one vocabulary
// (ruled lines, columns, ticks) instead of mixing a general-purpose pack.

function Icon({ size = 16, children, title, ...props }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : "true"}
      role={title ? "img" : undefined}
      focusable="false"
      {...props}
    >
      {title && <title>{title}</title>}
      {children}
    </svg>
  );
}

/* Brand: a ruled ledger page with a red double margin and a tick. */
export function BrandMark({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#f6f7f4" />
      <path d="M9 6v20M11.2 6v20" stroke="#c0392b" strokeWidth="1.3" />
      <path
        d="M14.5 10.5H25M14.5 15.5H25M14.5 20.5H20"
        stroke="#9fb7a6"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <path
        d="m19.5 21.2 2.3 2.3 4.7-5.2"
        fill="none"
        stroke="#17263a"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* Sample dataset: a bound ledger with ruled lines. */
export const LedgerIcon = (props) => (
  <Icon {...props}>
    <path d="M5 4.5h11.5A2.5 2.5 0 0 1 19 7v12.5H7.5A2.5 2.5 0 0 1 5 17z" />
    <path d="M5 17a2.5 2.5 0 0 1 2.5-2.5H19" />
    <path d="M9 8h6M9 11h4" />
  </Icon>
);

/* Your files: a sheet with an upward arrow. */
export const UploadIcon = (props) => (
  <Icon {...props}>
    <path d="M13.5 3.5H7A1.5 1.5 0 0 0 5.5 5v14A1.5 1.5 0 0 0 7 20.5h10a1.5 1.5 0 0 0 1.5-1.5V8.5z" />
    <path d="M13.5 3.5v5h5" />
    <path d="M12 17.5v-6M9.5 14 12 11.5l2.5 2.5" />
  </Icon>
);

/* Internal ledger file: a sheet with two money columns. */
export const SheetIcon = (props) => (
  <Icon {...props}>
    <rect x="4.5" y="3.5" width="15" height="17" rx="1.5" />
    <path d="M4.5 8.5h15M12 8.5v12M7 12h2.5M7 15.5h2.5M14.5 12H17M14.5 15.5H17" />
  </Icon>
);

/* Bank statement: a columned building. */
export const BankIcon = (props) => (
  <Icon {...props}>
    <path d="M3.5 9 12 4l8.5 5z" />
    <path d="M6 9.5v7M10 9.5v7M14 9.5v7M18 9.5v7M4 19.5h16" />
  </Icon>
);

export const PlayIcon = (props) => (
  <Icon {...props}>
    <path d="M8 5.5v13l10-6.5z" fill="currentColor" stroke="none" />
  </Icon>
);

export const DownloadIcon = (props) => (
  <Icon {...props}>
    <path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14" />
  </Icon>
);

export const ArrowUpRightIcon = (props) => (
  <Icon {...props}>
    <path d="M8 16 16 8M9.5 8H16v6.5" />
  </Icon>
);

export const ChevronLeftIcon = (props) => (
  <Icon {...props}>
    <path d="m14.5 6-6 6 6 6" />
  </Icon>
);

export const ChevronRightIcon = (props) => (
  <Icon {...props}>
    <path d="m9.5 6 6 6-6 6" />
  </Icon>
);

/* Nothing to show: an empty ruled sheet under a lens. */
export const EmptySheetIcon = (props) => (
  <Icon {...props}>
    <path d="M14 20.5H6.5A1.5 1.5 0 0 1 5 19V5a1.5 1.5 0 0 1 1.5-1.5h11A1.5 1.5 0 0 1 19 5v5" />
    <path d="M8.5 8h7M8.5 11.5h4" />
    <circle cx="16.5" cy="16.5" r="3" />
    <path d="m18.7 18.7 2 2" />
  </Icon>
);

export const CheckIcon = (props) => (
  <Icon {...props}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Icon>
);

export const CloseIcon = (props) => (
  <Icon {...props}>
    <path d="M6.5 6.5 17.5 17.5M17.5 6.5 6.5 17.5" />
  </Icon>
);

/* Reopen / reset: a counter-clockwise turn. */
export const UndoIcon = (props) => (
  <Icon {...props}>
    <path d="M5 9.5h9.5a4.5 4.5 0 0 1 0 9H9" />
    <path d="M8.5 6 5 9.5 8.5 13" />
  </Icon>
);

/* Review history: entries on a timeline. */
export const HistoryIcon = (props) => (
  <Icon {...props}>
    <circle cx="6" cy="6.5" r="1.6" />
    <circle cx="6" cy="17.5" r="1.6" />
    <path d="M6 8.1v7.8M10 6.5h9M10 17.5h9M10 10h6M10 21h5" />
  </Icon>
);

export const SparkIcon = (props) => (
  <Icon {...props}>
    <path d="M12 4.5c.6 3.8 3.7 6.9 7.5 7.5-3.8.6-6.9 3.7-7.5 7.5-.6-3.8-3.7-6.9-7.5-7.5 3.8-.6 6.9-3.7 7.5-7.5z" />
  </Icon>
);

export const KeyIcon = (props) => (
  <Icon {...props}>
    <circle cx="8" cy="15.5" r="3.5" />
    <path d="m10.5 13 8-8M15.5 8l2.5 2.5M13.5 10l1.5 1.5" />
  </Icon>
);

export const SearchIcon = (props) => (
  <Icon {...props}>
    <circle cx="10.5" cy="10.5" r="5.5" />
    <path d="m15 15 4.5 4.5" />
  </Icon>
);

/* Light theme: a sun with short rays. */
export const SunIcon = (props) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="3.8" />
    <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" />
  </Icon>
);

/* Dark theme: a crescent. */
export const MoonIcon = (props) => (
  <Icon {...props}>
    <path d="M19 14.5A7.5 7.5 0 0 1 9.5 5a7.5 7.5 0 1 0 9.5 9.5z" />
  </Icon>
);

/* Keyboard shortcuts: a keyboard outline with keys. */
export const KeyboardIcon = (props) => (
  <Icon {...props}>
    <rect x="3" y="6.5" width="18" height="11" rx="2" />
    <path d="M7 10h.01M10.5 10h.01M14 10h.01M17.5 10h.01M8 14h8" />
  </Icon>
);

/* Split settlement: one line fanning out into three. */
export const SplitIcon = (props) => (
  <Icon {...props}>
    <path d="M4 12h5M9 12c3 0 3-5.5 6-5.5h5M9 12h11M9 12c3 0 3 5.5 6 5.5h5" />
  </Icon>
);

/* Paired rows: two linked rings. */
export const LinkIcon = (props) => (
  <Icon {...props}>
    <path d="M10 14a4 4 0 0 0 5.7 0l2.8-2.8a4 4 0 0 0-5.7-5.7l-1 1" />
    <path d="M14 10a4 4 0 0 0-5.7 0l-2.8 2.8a4 4 0 0 0 5.7 5.7l1-1" />
  </Icon>
);

/* Triage: a funnel. */
export const FunnelIcon = (props) => (
  <Icon {...props}>
    <path d="M4 5.5h16l-6 7v5.5l-4 1.5v-7z" />
  </Icon>
);

/* Engine pipeline: stacked passes. */
export const LayersIcon = (props) => (
  <Icon {...props}>
    <path d="m12 4 8.5 4.5L12 13 3.5 8.5z" />
    <path d="m3.5 12.5 8.5 4.5 8.5-4.5M3.5 16.5 12 21l8.5-4.5" />
  </Icon>
);
