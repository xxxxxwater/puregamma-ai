import Image from "next/image";

type BrandLockupProps = {
  product?: "AI" | "Internal";
  size?: "standard" | "compact" | "small";
};

/** Shared PureGamma identity across navigation, landing, and account pages. */
export function BrandLockup({ product = "AI", size = "standard" }: BrandLockupProps) {
  return (
    <span className={`pg-brand-lockup pg-brand-lockup--${size}`}>
      <span className="pg-brand-mark" aria-hidden="true">
        <Image src="/logo.png" alt="" width={38} height={38} priority={false} />
      </span>
      <span className="pg-brand-wordmark">
        PureGamma{" "}<span className="pg-brand-suffix">{product}</span>
      </span>
    </span>
  );
}
