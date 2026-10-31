import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button, Card, Feedback } from "../components/ui";
import { CheckIcon } from "../components/icons";
import {
  createCheckoutSession,
  createPortalSession,
  getSubscriptionStatus,
  type SubscriptionStatus,
} from "../lib/api";
import { trackAction } from "../lib/analytics.ts";
import { useAppState } from "../state/useAppState";

export function Payment() {
  const { user } = useAppState();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<SubscriptionStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const paymentStatus = searchParams.get("status");

  useEffect(() => {
    if (paymentStatus === "success") {
      trackAction("payment_checkout_completed", { status: "success" });
    } else if (paymentStatus === "cancelled") {
      trackAction("payment_checkout_cancelled", { status: "cancelled" });
    }
  }, [paymentStatus]);

  useEffect(() => {
    let cancelled = false;
    getSubscriptionStatus()
      .then((data) => {
        if (!cancelled) {
          setStatus(data);
          trackAction("payment_page_viewed", { currentTier: data.tier });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load subscription details.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleUpgrade = async () => {
    setLoading(true);
    setError(null);
    trackAction("payment_checkout_started", { tier: "plus", price: "7.99 SGD", currency: "SGD" });
    try {
      const returnUrl = `${window.location.origin}/payment`;
      const res = await createCheckoutSession(returnUrl);
      if (res.checkoutUrl) {
        window.location.href = res.checkoutUrl;
      } else {
        throw new Error("No checkout URL returned.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open Stripe Checkout.");
      setLoading(false);
    }
  };

  const handleManage = async () => {
    setLoading(true);
    setError(null);
    trackAction("payment_portal_opened", { currentTier });
    try {
      const returnUrl = `${window.location.origin}/payment`;
      const res = await createPortalSession(returnUrl);
      if (res.portalUrl) {
        window.location.href = res.portalUrl;
      } else {
        throw new Error("No customer portal URL returned.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open Stripe Customer Portal.");
      setLoading(false);
    }
  };

  const currentTier = status?.tier ?? user?.tier ?? "beta";
  const isPlus = currentTier === "plus";

  return (
    <div style={{ maxWidth: "760px", margin: "0 auto", padding: "24px 16px" }}>
      <header style={{ marginBottom: "28px", textAlign: "center" }}>
        <h1 style={{ fontFamily: "var(--font-display, 'Baloo 2', sans-serif)", fontSize: "2rem", margin: "0 0 8px 0" }}>
          Linguini Subscriptions
        </h1>
        <p style={{ color: "var(--color-ink-muted, #64748b)", margin: 0, fontSize: "1rem" }}>
          Choose the learning pace that fits your daily routine.
        </p>
      </header>

      {paymentStatus === "success" && (
        <div style={{ marginBottom: "24px" }}>
          <Feedback tone="good">
            Your Plus subscription is active! Thank you for supporting Linguini.
          </Feedback>
        </div>
      )}

      {paymentStatus === "cancelled" && (
        <div style={{ marginBottom: "24px" }}>
          <Feedback tone="warn">
            Checkout was cancelled. No charges were made to your account.
          </Feedback>
        </div>
      )}

      {error && (
        <div style={{ marginBottom: "24px" }}>
          <Feedback tone="warn">
            {error}
          </Feedback>
        </div>
      )}

      {/* Plan Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "20px", marginBottom: "32px" }}>
        {/* Free Plan */}
        <Card lifted={currentTier === "free"} className="payment-card">
          <div style={{ padding: "8px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <h2 style={{ margin: 0, fontSize: "1.35rem", fontFamily: "var(--font-display, 'Baloo 2', sans-serif)" }}>Free Tier</h2>
              {currentTier === "free" && (
                <span style={{ fontSize: "0.75rem", padding: "2px 8px", background: "var(--color-teal-tint, #e0f2fe)", color: "var(--color-teal-dark, #0369a1)", borderRadius: "999px", fontWeight: 700 }}>
                  Current Plan
                </span>
              )}
            </div>
            <div style={{ fontSize: "1.8rem", fontWeight: 800, margin: "12px 0 16px 0", color: "var(--color-ink, #0f172a)" }}>
              $0 <span style={{ fontSize: "0.9rem", fontWeight: 400, color: "var(--color-ink-muted, #64748b)" }}>/ forever</span>
            </div>
            <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px 0", display: "flex", flexDirection: "column", gap: "10px" }}>
              <li style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.95rem" }}>
                <CheckIcon /> <strong>1 photo lesson</strong> per day
              </li>
              <li style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.95rem" }}>
                <CheckIcon /> Interactive I-Spy vocabulary review
              </li>
              <li style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.95rem" }}>
                <CheckIcon /> Daily language journal
              </li>
            </ul>
            {currentTier === "free" ? (
              <Button variant="quiet" block disabled>
                Active
              </Button>
            ) : (
              <Button variant="quiet" block disabled>
                Included
              </Button>
            )}
          </div>
        </Card>

        {/* Plus Plan */}
        <div style={{ border: isPlus ? "2px solid var(--color-tomato, #ef4444)" : "2px solid #fed7aa", borderRadius: "16px", overflow: "hidden" }}>
          <Card lifted={isPlus} className="payment-card">
            <div style={{ padding: "8px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                <h2 style={{ margin: 0, fontSize: "1.35rem", fontFamily: "var(--font-display, 'Baloo 2', sans-serif)", color: "var(--color-tomato, #ef4444)" }}>
                  Plus Tier
                </h2>
                {isPlus && (
                  <span style={{ fontSize: "0.75rem", padding: "2px 8px", background: "var(--color-tomato, #ef4444)", color: "#ffffff", borderRadius: "999px", fontWeight: 700 }}>
                    Active
                  </span>
                )}
              </div>
              <div style={{ fontSize: "1.8rem", fontWeight: 800, margin: "12px 0 16px 0", color: "var(--color-ink, #0f172a)" }}>
                $7.99 SGD <span style={{ fontSize: "0.9rem", fontWeight: 400, color: "var(--color-ink-muted, #64748b)" }}>/ month</span>
              </div>
              <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px 0", display: "flex", flexDirection: "column", gap: "10px" }}>
                <li style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.95rem" }}>
                  <CheckIcon /> <strong>10 photo lessons</strong> per day
                </li>
                <li style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.95rem" }}>
                  <CheckIcon /> Unlimited vocabulary & grammar challenges
                </li>
                <li style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.95rem" }}>
                  <CheckIcon /> Priority AI model response generation
                </li>
                <li style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.95rem" }}>
                  <CheckIcon /> Invoices, receipt downloads & self-serve cancellation
                </li>
              </ul>

              {isPlus ? (
                <Button variant="secondary" block onClick={handleManage} disabled={loading}>
                  {loading ? "Opening Portal…" : "Manage Subscription & Invoices"}
                </Button>
              ) : (
                <Button variant="primary" block onClick={handleUpgrade} disabled={loading}>
                  {loading ? "Redirecting to Stripe…" : "Upgrade to Plus"}
                </Button>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
