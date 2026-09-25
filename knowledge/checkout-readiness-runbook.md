# Checkout API readiness failures

Symptoms:

- Kubernetes readiness probe returns HTTP 503.
- The checkout API depends on payment-gateway.

Initial investigation:

1. Inspect recent deployment changes.
2. Inspect pod events and readiness probe failures.
3. Check payment-gateway latency and error rate.
4. Compare failure timing against recent deployments.
5. Do not restart production workloads without an approved incident procedure.
