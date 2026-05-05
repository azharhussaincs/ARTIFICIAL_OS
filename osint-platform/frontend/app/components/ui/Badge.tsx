import { CheckCircle2, ShieldOff } from "lucide-react";

export function VerifiedBadge({ verified }: { verified: boolean }) {
  return verified ? (
    <span className="verified-pill"><CheckCircle2 className="w-3 h-3" /> verified</span>
  ) : (
    <span className="unverified-pill"><ShieldOff className="w-3 h-3" /> unverified</span>
  );
}
