import { useState } from "react";
import { Crown, X, MousePointerClick } from "lucide-react";
import { initials, photoUrl } from "./utils";

type Highlight = "winner" | "loser" | "neutral";

interface FighterAvatarProps {
  name: string;
  highlight?: Highlight;
  markable?: boolean;
  onMark?: () => void;
  size?: number;
}

export function FighterAvatar({
  name, highlight = "neutral", markable = false, onMark, size = 64,
}: FighterAvatarProps) {
  const [broken, setBroken] = useState(false);

  const ring =
    highlight === "winner"
      ? "border-success shadow-[0_0_18px_-2px_var(--color-success)]"
      : highlight === "loser"
        ? "border-border opacity-50"
        : "border-border";

  const Wrapper = markable ? "button" : "div";

  return (
    <Wrapper
      onClick={markable ? onMark : undefined}
      className={[
        "relative rounded-full overflow-hidden border-2 transition-all group/avatar",
        ring,
        markable ? "cursor-pointer hover:border-accent" : "",
      ].join(" ")}
      style={{ width: size, height: size }}
      title={markable ? "Marcar ganador" : name}
    >
      {!broken ? (
        <img
          src={photoUrl(name)}
          alt={name}
          className="w-full h-full object-cover object-top"
          onError={() => setBroken(true)}
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center bg-white/5 text-muted-foreground font-display text-lg">
          {initials(name)}
        </div>
      )}

      {highlight === "winner" && (
        <span className="absolute -top-1 -right-1 bg-success text-background rounded-full p-0.5">
          <Crown size={12} />
        </span>
      )}
      {highlight === "loser" && (
        <span className="absolute -top-1 -right-1 bg-destructive/80 text-white rounded-full p-0.5">
          <X size={12} />
        </span>
      )}
      {markable && (
        <span className="absolute inset-0 hidden group-hover/avatar:flex items-center justify-center bg-black/40 text-accent">
          <MousePointerClick size={18} />
        </span>
      )}
    </Wrapper>
  );
}
