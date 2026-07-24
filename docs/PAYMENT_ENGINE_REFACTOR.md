# Vidalys Pay — Multi-provider Payment Engine

## Decision

Vidalys Pay will evolve from an internal Pagar.me payment-link generator into the shared payment orchestration engine for Vidalys applications.

The first consumer will be Flowlog. Future consumers may include Mérito and other Vidalys products that need payments.

The engine will initially support:

- Pagar.me
- Mercado Pago

Pagar.me remains the current production provider, but business use cases must no longer import or instantiate `PagarmeClient` directly.

## Product boundary

Vidalys Pay is responsible for:

- creating hosted checkout/payment links;
- tracking payment state;
- receiving and normalizing provider webhooks;
- canceling links when supported;
- requesting refunds when supported;
- keeping provider attempt history and audit data;
- delivering signed outbound webhooks to consumer applications;
- managing payment-provider connections per organization.

Vidalys Pay is not responsible for:

- orders, fulfillment, shipping, stock or customer CRM;
- manually received cash, direct PIX or card-terminal payments;
- holding or redistributing client funds without a formal marketplace/PSP model;
- forcing every provider to expose exactly the same capabilities.

## Core concepts

### Organization

The merchant or business that owns the financial operation.

### Seller

A person who operates the system on behalf of an organization.

### ClientApplication

A system consuming Vidalys Pay, such as Flowlog, the standalone Vidalys Pay panel or n8n.

### ApiCredential

A credential owned by a ClientApplication. It inherits organization ownership and scopes from that application. The caller must not gain access to arbitrary sellers by supplying a `seller_id`.

### GatewayConnection

An organization-specific connection to a financial provider.

Examples:

- Bibelô / Pagar.me / production
- Pilot Store / Mercado Pago / production

Provider credentials must be encrypted at rest and must not remain exclusively as global environment variables once multiple organizations are supported.

### Payment

The provider-independent aggregate representing a charge requested by a client application.

### CheckoutSession

A hosted checkout/payment-link representation. One Payment may have one or more checkout sessions over its lifecycle.

### PaymentAttempt

A provider transaction attempt associated with a Payment.

### ProviderWebhookEvent

A raw inbound event received from Pagar.me, Mercado Pago or another provider.

### DomainEvent

A normalized internal event such as:

- `payment.created`
- `payment.pending`
- `payment.paid`
- `payment.failed`
- `payment.canceled`
- `payment.expired`
- `payment.refunded`
- `payment.chargeback`

### WebhookEndpoint and WebhookDelivery

Configuration and delivery history for signed outbound events sent by Vidalys Pay to Flowlog or another ClientApplication.

## Provider contract

The domain layer must depend on a provider-neutral contract.

```python
class PaymentProvider(Protocol):
    code: str

    def capabilities(self) -> set[str]: ...
    def create_checkout(self, command: CreateCheckoutCommand) -> CheckoutResult: ...
    def get_payment(self, provider_reference: str) -> ProviderPaymentResult: ...
    def cancel_checkout(self, provider_reference: str) -> ProviderOperationResult: ...
    def refund_payment(self, command: RefundCommand) -> ProviderOperationResult: ...
    def verify_webhook(self, request: ProviderWebhookRequest) -> VerifiedWebhook: ...
    def normalize_webhook(self, webhook: VerifiedWebhook) -> list[NormalizedProviderEvent]: ...
```

Implementations:

```text
PagarmeProvider
MercadoPagoProvider
```

Use cases must resolve a provider through a registry and a GatewayConnection. They must not instantiate provider HTTP clients directly.

## Capability model

Providers are not identical. The engine must expose capabilities instead of pretending every operation exists everywhere.

Initial capability names:

```text
hosted_checkout
credit_card
pix
boleto
installments
cancel_checkout
full_refund
partial_refund
webhooks
seller_oauth
split
```

An API request that requires an unsupported capability returns a stable domain error such as `provider_capability_not_supported`.

## API direction

Consumer applications authenticate with their own ApiCredential.

Example:

```http
POST /api/v1/payments/
Authorization: Bearer <application-key>
Idempotency-Key: flowlog:sale:9821:payment:1
```

```json
{
  "external_reference": "sale_9821",
  "amount_cents": 35000,
  "currency": "BRL",
  "checkout": {
    "payment_methods": ["credit_card"],
    "max_installments": 3,
    "expires_in_minutes": 1440
  },
  "customer": {
    "name": "Maria Silva",
    "phone": "+5531999999999"
  },
  "metadata": {
    "flowlog_sale_id": "sale_9821"
  }
}
```

The organization and allowed GatewayConnection are derived from the credential, not from an arbitrary `seller_id` supplied by the caller.

## Outbound webhook contract

Vidalys Pay sends normalized events to the application that created the payment.

Headers:

```text
X-Vidalys-Event-ID
X-Vidalys-Timestamp
X-Vidalys-Signature
```

Example payload:

```json
{
  "id": "evt_01...",
  "type": "payment.paid",
  "created_at": "2026-07-24T09:00:00Z",
  "data": {
    "payment_id": "pay_01...",
    "external_reference": "sale_9821",
    "amount_cents": 35000,
    "currency": "BRL",
    "status": "paid",
    "provider": "pagarme",
    "paid_at": "2026-07-24T08:59:40Z"
  }
}
```

Deliveries use HMAC signatures, permanent event IDs, retry/backoff, delivery logs and manual resend.

## Flowlog integration boundary

Flowlog owns:

- sale/order;
- customer and seller workflow;
- manual payment records;
- fulfillment and delivery;
- its own payment summary.

Vidalys Pay owns:

- provider checkout creation;
- provider credentials;
- provider webhook processing;
- normalized payment state;
- financial attempt history;
- outbound payment events.

Manual methods such as cash, direct PIX and card terminal remain inside Flowlog and do not call Vidalys Pay.

## Merchant onboarding strategy

### Initial stage

- One Organization: Bibelô.
- Existing Pagar.me account remains active.
- Mercado Pago is added as a second adapter and tested separately.
- Flowlog receives an application credential restricted to Bibelô.

### SaaS stage

Each independent merchant connects its own provider account:

- Mercado Pago through OAuth when available for the selected integration;
- Pagar.me through the account/credential model supported commercially for that merchant;
- encrypted organization-specific credentials where OAuth is unavailable.

Do not route unrelated merchants through Bibelô's credentials.

### Marketplace stage — not part of this refactor

Holding or splitting funds for multiple merchants requires a separate commercial, compliance and provider-onboarding decision. It must not be introduced implicitly by the multi-provider abstraction.

## Migration sequence

### Phase 1 — Ownership and authorization

1. Add Organization.
2. Add OrganizationMembership if administrative users need organization access.
3. Link Seller to Organization.
4. Add ClientApplication and ApiCredential.
5. Replace unrestricted API-key plus `seller_id` authorization.
6. Add organization ownership to PaymentLink, Boleto, webhook and notification records.
7. Change idempotency scope from seller-only to organization/application.

### Phase 2 — Provider abstraction

1. Add provider DTOs and domain errors.
2. Add PaymentProvider protocol.
3. Add ProviderRegistry.
4. Add GatewayConnection.
5. Wrap the existing Pagar.me client in PagarmeProvider.
6. Refactor payment-link creation to resolve the provider through GatewayConnection.
7. Refactor boleto creation through a provider capability instead of importing Pagar.me.
8. Keep behavior unchanged for the existing Pagar.me production flow.

### Phase 3 — Normalized inbound events

1. Split provider-specific webhook receivers.
2. Verify each provider using its own strategy.
3. Store provider plus connection ownership on raw events.
4. Normalize provider payloads before domain state transitions.
5. Make provider event identifiers unique by provider/connection, not globally.

### Phase 4 — Outbound application webhooks

1. Add WebhookEndpoint.
2. Add DomainEvent.
3. Add WebhookDelivery.
4. Reuse the outbox worker with a new `application_webhook.send` topic.
5. Add HMAC signatures, retry/backoff and manual resend.
6. Add webhook event documentation and contract tests.

### Phase 5 — Mercado Pago

1. Add MercadoPagoProvider.
2. Create Checkout Pro preferences for hosted checkout.
3. Add Mercado Pago webhook verification and normalization.
4. Add OAuth connection flow for independent sellers when adopted.
5. Run provider contract tests against both adapters.

### Phase 6 — Flowlog integration

1. Create a restricted Flowlog ClientApplication credential.
2. Create payment from a Flowlog sale.
3. Store Vidalys payment ID and checkout URL in Flowlog.
4. Receive and deduplicate signed Vidalys events.
5. Update Flowlog payment state without importing provider-specific fields.

## Compatibility strategy

During the refactor:

- existing seller sessions and standalone screens remain functional;
- the current Pagar.me account remains the default connection for Bibelô;
- existing `/api/v1/payment-links/` behavior is preserved until a versioned replacement is ready;
- new integration contracts should be introduced under a new API version or behind explicit compatibility adapters;
- no provider migration is performed automatically.

## Acceptance criteria

The refactor is considered structurally complete when:

1. No payment or boleto use case imports `PagarmeClient` directly.
2. Every payment operation resolves an organization-owned GatewayConnection.
3. An API credential cannot access another organization by changing a request identifier.
4. Pagar.me and Mercado Pago pass the same provider contract test suite for shared capabilities.
5. Provider-specific webhook payloads never reach Flowlog.
6. Flowlog receives signed, idempotent normalized payment events.
7. Manual payments continue to work entirely inside Flowlog.
