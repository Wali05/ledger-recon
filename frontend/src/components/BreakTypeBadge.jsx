export default function BreakTypeBadge({ type }) {
  return (
    <span className={`badge badge-${type}`}>{type?.replaceAll("_", " ")}</span>
  );
}
