import { BasilIcon } from "./icons";
import "./gamification.css";

export function QuestionBasil({ amount }: { amount?: number }) {
  return amount && amount > 0 ? <strong className="question-basil" role="status"><BasilIcon size={17} />+{amount} Basil earned</strong> : null;
}
