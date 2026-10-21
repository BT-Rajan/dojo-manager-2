import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { PortalError, portalApi } from "./api";
import { useLang } from "./i18n";
import { AlertIcon, Eyebrow } from "./ui";

const RESEND_WAIT = 42; // seconds before "Resend code" works again

function spaced(mobile: string) {
  // +96555551111 -> +965 5555 1111
  return `${mobile.slice(0, 4)} ${mobile.slice(4, 8)} ${mobile.slice(8)}`;
}

/** Sign in with a mobile number and a 4-digit WhatsApp code. No passwords. */
export function SignIn() {
  const { t, lang } = useLang();
  const qc = useQueryClient();
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [typed, setTyped] = useState("");
  const [mobile, setMobile] = useState("");
  const [digits, setDigits] = useState(["", "", "", ""]);
  const [error, setError] = useState<string | null>(null);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [wait, setWait] = useState(0);
  const inputs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    if (wait <= 0) return;
    const id = window.setTimeout(() => setWait(wait - 1), 1000);
    return () => window.clearTimeout(id);
  }, [wait]);

  const send = async (number: string) => {
    setBusy(true);
    setError(null);
    try {
      const r = await portalApi<{ mobile: string; test_message: string | null }>("/api/portal/send-code", {
        method: "POST",
        body: { mobile: number, lang },
      });
      setMobile(r.mobile);
      setTestMessage(r.test_message);
      setDigits(["", "", "", ""]);
      setStep("code");
      setWait(RESEND_WAIT);
      window.setTimeout(() => inputs.current[0]?.focus(), 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const verify = async (code: string) => {
    setBusy(true);
    setError(null);
    try {
      await portalApi("/api/portal/verify", { method: "POST", body: { mobile, code, lang } });
      await qc.invalidateQueries({ queryKey: ["/api/portal/me"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      if (e instanceof PortalError && e.testMessage) {
        setTestMessage(e.testMessage);
        setWait(RESEND_WAIT);
      }
      setDigits(["", "", "", ""]);
      window.setTimeout(() => inputs.current[0]?.focus(), 0);
    } finally {
      setBusy(false);
    }
  };

  const setDigit = (i: number, value: string) => {
    const only = value.replace(/\D/g, "");
    if (only.length > 1) {
      // Pasted or autofilled the whole code.
      const next = only.slice(0, 4).split("");
      const filled = [0, 1, 2, 3].map((k) => next[k] ?? "");
      setDigits(filled);
      if (filled.every(Boolean)) void verify(filled.join(""));
      else inputs.current[next.length]?.focus();
      return;
    }
    const next = [...digits];
    next[i] = only;
    setDigits(next);
    if (only && i < 3) inputs.current[i + 1]?.focus();
    if (next.every(Boolean)) void verify(next.join(""));
  };

  const submitPhone = (e: FormEvent) => {
    e.preventDefault();
    void send(typed);
  };
  const submitCode = (e: FormEvent) => {
    e.preventDefault();
    void verify(digits.join(""));
  };

  return (
    <div className="ea-block" style={{ paddingBlock: 32 }}>
      <div className="ea-wrap ea-wrap--narrow">
        {testMessage && (
          <div className="ea-testmode" role="note" style={{ marginBlockEnd: 16 }}>
            {t("TEST MODE — WhatsApp isn't connected yet. The message would say:", "وضع تجريبي — واتساب غير متصل بعد. نص الرسالة:")}{" "}
            <span dir="auto">{testMessage}</span>
          </div>
        )}
        {step === "code" ? (
          <>
            <form className="ea-form" onSubmit={submitCode} noValidate>
              <div style={{ display: "grid", gap: 6 }}>
                <Eyebrow>{t("Member portal", "بوابة الأعضاء")}</Eyebrow>
                <h1 className="ea-h1">{t("Enter your code", "أدخل الرمز")}</h1>
              </div>
              <fieldset className="ea-field" aria-describedby={error ? "otp-err" : undefined}>
                <legend className="ea-label">{t("Enter the 4-digit code", "أدخل الرمز المكوّن من 4 أرقام")}</legend>
                <span className="ea-hint">
                  {t("Sent by WhatsApp to", "أُرسل عبر واتساب إلى")} <span dir="ltr">{spaced(mobile)}</span>
                </span>
                <div className="ea-otp">
                  {digits.map((d, i) => (
                    <input
                      key={i}
                      ref={(el) => (inputs.current[i] = el)}
                      value={d}
                      inputMode="numeric"
                      autoComplete={i === 0 ? "one-time-code" : "off"}
                      pattern="[0-9]*"
                      maxLength={i === 0 ? 4 : 1}
                      aria-label={lang === "ar" ? `الرقم ${i + 1}` : `Digit ${i + 1}`}
                      aria-invalid={error ? true : undefined}
                      onChange={(e) => setDigit(i, e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Backspace" && !digits[i] && i > 0) inputs.current[i - 1]?.focus();
                      }}
                    />
                  ))}
                </div>
                {error && (
                  <span className="ea-err" id="otp-err" role="alert">
                    <AlertIcon />
                    {error}
                  </span>
                )}
              </fieldset>
              <button type="submit" className="ea-btn ea-btn--primary ea-btn--block" disabled={busy || !digits.every(Boolean)}>
                {t("Sign in", "دخول")}
              </button>
            </form>
            <button
              type="button"
              className="ea-btn ea-btn--ghost ea-btn--block"
              style={{ marginBlockStart: 8 }}
              disabled={busy || wait > 0}
              onClick={() => void send(mobile)}
            >
              {t("Resend code", "إعادة إرسال الرمز")}
              {wait > 0 && <span dir="ltr"> ({wait})</span>}
            </button>
            <p className="ea-meta" style={{ marginBlockStart: 12 }}>
              <a
                href="/portal"
                onClick={(e) => {
                  e.preventDefault();
                  setStep("phone");
                  setError(null);
                  setTestMessage(null);
                }}
              >
                {t("Use a different number", "استخدم رقماً آخر")}
              </a>
            </p>
          </>
        ) : (
          <form className="ea-form" onSubmit={submitPhone} noValidate>
            <div style={{ display: "grid", gap: 6 }}>
              <Eyebrow>{t("Member portal", "بوابة الأعضاء")}</Eyebrow>
              <h1 className="ea-h1">{t("Welcome back", "أهلاً بعودتك")}</h1>
              <p className="ea-meta">
                {t(
                  "Sign in with your mobile number. No passwords: we'll send a code by WhatsApp.",
                  "ادخل برقم جوالك. بدون كلمة مرور: سنرسل لك رمزاً عبر واتساب.",
                )}
              </p>
            </div>
            <div className="ea-field">
              <label className="ea-label" htmlFor="mp">
                {t("Mobile number", "رقم الجوال")}
              </label>
              <div className="ea-phone">
                <span className="ea-cc" dir="ltr">
                  +965
                </span>
                <input
                  className="ea-input"
                  id="mp"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel-national"
                  dir="ltr"
                  maxLength={20}
                  placeholder="0000 0000"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  aria-describedby={`mp-hint${error ? " mp-err" : ""}`}
                  aria-invalid={error ? true : undefined}
                />
              </div>
              <span className="ea-hint" id="mp-hint">
                {t("The number you registered with the academy.", "الرقم المسجّل لدى الأكاديمية.")}
              </span>
              {error && (
                <span className="ea-err" id="mp-err" role="alert">
                  <AlertIcon />
                  {error}
                </span>
              )}
            </div>
            <button type="submit" className="ea-btn ea-btn--primary ea-btn--block" disabled={busy}>
              {t("Send code", "أرسل الرمز")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
