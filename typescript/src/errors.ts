export type ErrorKind = "UnknownField" | "Unsupported" | "InvalidRequest" | "InvalidSchema" | "LimitExceeded";

/** The stage that refused a request, in the vocabulary of the spec's rejection.schema.json. */
export type RejectedAt = "allowlist" | "resourceLimits" | "typeCoercion" | "requestParsing";

export type RejectionReason =
  | "unknown-field"
  | "field-not-filterable"
  | "max-depth-exceeded"
  | "max-leaves-exceeded"
  | "max-in-values-exceeded"
  | "max-page-size-exceeded"
  | "uncoercible-value"
  | "unknown-operator"
  | "duplicate-output-name"
  | "malformed-request";

export interface Rejection {
  readonly rejectedAt: RejectedAt;
  readonly reason: RejectionReason;
}

/** A request or schema the compiler refuses. The kind is a free label for the runner's report; the message says why. */
export class CompileError extends Error {
  readonly kind: ErrorKind;
  readonly rejectedAt: RejectedAt | undefined;
  readonly reason: RejectionReason | undefined;

  constructor(kind: ErrorKind, message: string, rejection?: Rejection) {
    super(message);
    this.name = "CompileError";
    this.kind = kind;
    this.rejectedAt = rejection?.rejectedAt;
    this.reason = rejection?.reason;
  }
}
