import type { ReactNode } from "react";
import type { Classification, Confidence } from "@/lib/types";

export type Tone = "neutral" | "cyan" | "amber" | "green" | "red" | "mag";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "",
  cyan: "chip-cyan",
  amber: "chip-amber",
  green: "chip-green",
  red: "chip-red",
  mag: "chip-mag",
};

export default function Badge({
  tone = "neutral",
  title,
  children,
  className = "",
}: {
  tone?: Tone;
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={`chip ${TONE_CLASS[tone]} ${className}`} title={title}>
      {children}
    </span>
  );
}

export function confidenceTone(c: Confidence): Tone {
  switch (c) {
    case "strong":
      return "green";
    case "moderate":
      return "cyan";
    case "low":
      return "amber";
    default:
      return "neutral";
  }
}

export function classificationTone(c: Classification): Tone {
  switch (c) {
    case "unexplained_needs_review":
      return "amber";
    case "likely_artifact":
      return "red";
    case "known_high_pm_star":
    case "known_variable":
    case "known_no_change":
    case "solar_system_object":
      return "cyan";
    case "low_confidence_change":
      return "amber";
    default:
      return "neutral";
  }
}
