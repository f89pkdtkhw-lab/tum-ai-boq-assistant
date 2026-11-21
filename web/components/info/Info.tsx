import { Icon } from "../icon/Icon";

/** Explanation on demand (HIG progressive disclosure): an ⓘ next to a heading; the text shows on hover or keyboard focus. */
export function Info({ text }: { text: string }) {
  return (
    <span className="info" tabIndex={0} role="note" aria-label={text} data-tip={text}>
      <Icon name="help" size={14} />
    </span>
  );
}
