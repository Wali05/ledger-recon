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
