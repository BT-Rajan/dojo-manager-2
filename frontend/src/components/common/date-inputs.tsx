import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { fmtDate, parseDmy, parseHms } from "@/lib/format";
import { cn } from "@/lib/utils";

type Props = {
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  className?: string;
  "aria-label"?: string;
};

/**
 * Text entry in a fixed format, independent of the browser locale. `value`/`onChange` use
 * the API format; the user sees and types the display format. Invalid text is flagged and
 * reported upwards as "" so forms can block submission.
 */
function FormattedInput({
  value,
  onChange,
  toText,
  parse,
  placeholder,
  maxLength,
  required,
  className,
  ...rest
}: Props & {
  toText: (v: string) => string;
  parse: (t: string) => string | null;
  placeholder: string;
  maxLength: number;
}) {
  const [text, setText] = useState(() => (value ? toText(value) : ""));
  useEffect(() => {
    // Follow external changes (e.g. a form reset) without clobbering partial typing.
    if (value && parse(text) !== value) setText(toText(value));
    if (!value && parse(text)) setText("");
  }, [value]);
  const invalid = text !== "" && parse(text) === null;
  return (
    <Input
      inputMode="numeric"
      placeholder={placeholder}
      maxLength={maxLength}
      value={text}
      required={required}
      aria-invalid={invalid}
      aria-label={rest["aria-label"]}
      className={cn(invalid && "border-red-500 focus-visible:ring-red-500", className)}
      onChange={(e) => {
        setText(e.target.value);
        onChange(parse(e.target.value) ?? "");
      }}
      onBlur={() => {
        const parsed = parse(text);
        if (parsed) setText(toText(parsed));
      }}
    />
  );
}

/** Date as DD-MM-YYYY; value is ISO "YYYY-MM-DD" (or "" when empty/invalid). */
export function DateInput(props: Props) {
  return <FormattedInput {...props} toText={fmtDate} parse={parseDmy} placeholder="DD-MM-YYYY" maxLength={10} />;
}

/** Time as HH:mm:ss (24-hour); value is "HH:mm:ss". "HH:mm" is accepted and completed. */
export function TimeInput(props: Props) {
  return <FormattedInput {...props} toText={(v) => v} parse={parseHms} placeholder="HH:MM:SS" maxLength={8} />;
}

/** Month as MM-YYYY; value is "YYYY-MM". */
export function MonthInput(props: Props) {
  return (
    <FormattedInput
      {...props}
      toText={(v) => `${v.slice(5, 7)}-${v.slice(0, 4)}`}
      parse={(t) => {
        const m = /^(0[1-9]|1[0-2])-(\d{4})$/.exec(t.trim());
        return m ? `${m[2]}-${m[1]}` : null;
      }}
      placeholder="MM-YYYY"
      maxLength={7}
    />
  );
}
