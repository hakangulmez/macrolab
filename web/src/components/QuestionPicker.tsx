import { questions, type Question } from "../simpleAnalysis";
export function QuestionPicker({
  value,
  select,
}: {
  value?: Question | null;
  select: (q: Question) => void;
}) {
  return (
    <div className="question-picker" role="group" aria-label="Question type">
      {questions.map(([id, label]) => (
        <button
          key={id}
          data-testid={`question-${id}`}
          aria-pressed={value === id}
          onClick={() => select(id)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
